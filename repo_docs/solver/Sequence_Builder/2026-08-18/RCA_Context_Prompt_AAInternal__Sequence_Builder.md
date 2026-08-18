# RCA Context Prompt: Sequence Builder Incident Observer

## 1. System Blueprint & Tech Stack
*   **Core Runtime**: Java 17+, Spring Boot 3.x (Web MVC, Scheduling, DI).
*   **Event Bus**: Apache Kafka (Ingestion: `KafkaConsumerService`, Outbound: `KafkaProducerService`).
*   **Optimization Engine**: FICO Xpress (JNI/C++ native bindings) via `OptModel`.
*   **Persistence**: Spring Data JPA (`LegDataRepository`, `OutputDataRepository`), Azure Blob Storage (`AzureBlobRepositoryImpl`).
*   **External Integrations**: QLA REST Client, MS Teams Notifications, FOS HTTP Scripting.
*   **Deployment**: Kubernetes (Containerized).
*   **Key Classes**: `SequenceBuilderApplication`, `HttpSolverController`, `OptimizationService`, `ShortestPathComponent`.

## 2. Architectural Advantages & Safeguards
*   **Decoupled Processing**: Kafka enables asynchronous scaling of solver tasks independent of the REST API.
*   **Modular Rule Engine**: Regulatory logic (FAR 121, WOCL) is encapsulated in discrete classes (`FAR121RestTimeRule`, `WOCL`), facilitating isolated testing.
*   **State Management**: `RunStateManager` provides explicit control over run lifecycles (snapshots, kill flags) for graceful shutdowns.
*   **Observability**: Integrated MS Teams notifications trigger on critical failures (`KillRunException`).
*   **Serialization**: Jackson handles robust JSON mapping for complex domain objects (`FlightDutyPeriod`, `ProjectedData`).

## 3. Architectural Limitations
*   **Native Memory Leaks**: `OptModel` lacks explicit JNI cleanup (`finally` blocks) for FICO Xpress resources (`XPRSprob`, `XPRB`), causing native heap growth on failure/interruption.
*   **Connection Pool Exhaustion**: `LegDataRepositoryImpl.connectToFOS` instantiates `HttpURLConnection` without guaranteed `disconnect()` in all exception paths.
*   **GC Pressure Spikes**: `ShortestPathComponent` performs aggressive `deepCopy` of `DutyInfo` lists inside nested loops, generating massive object churn.
*   **Mutable State Hazards**: Validation rules (`PilotRedeyeRule`) mutate shared input objects (`UnsequencedLegPairing`), risking race conditions in concurrent processing.
*   **Algorithmic Inefficiency**: `FSOUtil.daysBetween` uses O(N) linear scanning instead of O(1) `ChronoUnit`.
*   **Azure Client Overhead**: `AzureBlobRepositoryImpl` creates clients per method call; requires verification against pooling strategies for high throughput.
*   **State TTL Absence**: In-memory `labelsMap` structures lack Time-To-Live (TTL) mechanisms, risking OOM in streaming/migration scenarios.

## 4. Failure Modes & Diagnostics (RCA Triage Cheatsheet)

| Symptom Category | Potential Root Cause | Primary File/Class | Diagnostic Evidence / Citation |
| :--- | :--- | :--- | :--- |
| **Native Heap OOM / Crash** | JNI Memory Leak (FICO Xpress) | `OptModel.java` | Missing `finally` block; `runModel` does not call `model.close()` or `XPRSend`. |
| **Socket Exhaustion / Connection Timeout** | HTTP Resource Leak | `LegDataRepositoryImpl.java` | `connectToFOS` lacks `conn.disconnect()` in `catch`/`finally`; `HttpURLConnection` leaked on exceptions. |
| **CPU Spikes / High GC Frequency** | Object Churn / Deep Copy | `ShortestPathComponent.java` | `identifyDhdFromBase`/`identifyDhdToBase` loop creates new `UnsequencedLegPairing` + `deepCopy` of entire `DutyInfo` list. |
| **Data Corruption / Incorrect Legality** | Mutable State Race Condition | `PilotRedeyeRule.java` | `checkRedeyeDuty` mutates `dutyPeriod.setRedeye(true)` on shared input objects; side effects in concurrent threads. |
| **Latency Spikes (Simple Calc)** | Inefficient Date Logic | `FSOUtil.java` | `daysBetween` uses O(N) `while` loop instead of `ChronoUnit.DAYS.between`. |
| **Slow Blob Writes / Connection Saturation** | Azure Client Instantiation | `AzureBlobRepositoryImpl.java` | `saveData` creates new `BlobClient` per call; verify if pooling is required for high throughput. |
| **Memory Growth (Streaming Context)** | Missing State TTL | `ShortestPathComponent.java` | `labelsMap` grows indefinitely without TTL; risk if migrated to Flink/streaming. |

**Immediate Action Protocol**:
1.  **Check Native Heap**: Monitor `native_memory_usage` metrics; correlate spikes with `OptModel` execution logs.
2.  **Verify Thread Safety**: Inspect `PilotRedeyeRule` execution context; look for concurrent access to `UnsequencedLegPairing`.
3.  **Audit Connections**: Check open socket counts; correlate with `LegDataRepositoryImpl` error logs.
4.  **GC Analysis**: Review GC logs for "Full GC" frequency; correlate with `ShortestPathComponent` loop iterations.