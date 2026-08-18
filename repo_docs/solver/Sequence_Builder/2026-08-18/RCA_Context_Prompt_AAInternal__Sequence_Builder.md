# RCA Context Prompt: Sequence_Builder Incident Observer

## 1. System Blueprint & Tech Stack
*   **Core Runtime**: Spring Boot (Java), Entry: `SequenceBuilderApplication`.
*   **Event Bus**: Apache Kafka (`AAInternal` mesh). Consumer: `KafkaConsumerService` (Manual ACK, async delegation). Producer: `KafkaProducerService` (Compressed JSON).
*   **API Layer**: Spring MVC (`HttpSolverController`, `KillController`, `FlightController`).
*   **Data Access**: JPA/Spring Data (`LegDataRepository`), Custom DTOs (`FlightLeg`, `UnsequencedLeg`).
*   **External Integrations**:
    *   **FICO Xpress**: Native C++ Optimizer via `OptModel` (JNI).
    *   **Azure Blob Storage**: `AzureBlobRepositoryImpl`.
    *   **FOS Service**: REST via `HttpURLConnection` in `LegDataRepositoryImpl`.
*   **Key Metrics**: 196 Classes, 710 Methods, High-throughput flight sequencing.

## 2. Architectural Advantages & Safeguards
*   **Fault Tolerance**: Manual Kafka ACK (`ack.acknowledge()`) ensures at-least-once delivery; `RunStateManager` tracks run lifecycle.
*   **Telemetry**: `TeamsNotification` triggers on `KillRunException` or `InvalidUserInputException`.
*   **Modularity**: Strict separation (Controllers/Services/Repositories) with `@EnableScheduling` for background sync.
*   **Payload Optimization**: `CompressUtil` reduces Kafka message size for large solver responses.
*   **Observability**: Structured logging via SLF4J/Logback; Swagger/OpenAPI for API contract visibility.

## 3. Architectural Limitations
*   **Native Memory Leaks**: `OptModel` lacks explicit `close()`/`dispose()` for FICO Xpress native objects in `finally` blocks.
*   **Resource Exhaustion**: `HttpURLConnection` in `LegDataRepositoryImpl` not guaranteed closed on exception paths; `BlobClient` instantiated per call in `AzureBlobRepositoryImpl` (no pooling).
*   **GC Pressure**: Excessive `DutyInfo::deepCopy` in `ShortestPathComponent` loops; O(N) date calculation in `FSOUtil`.
*   **Mutable State Hazards**: `PilotRedeyeRule` mutates shared `UnsequencedLegPairing` objects during validation (race condition risk).
*   **State Bloat**: In-memory Maps (`labelsMap`, `dhdHM`) lack TTL/eviction policies.
*   **Parallelism Limits**: Concurrency limited by manual thread management and native lock contention in FICO.

## 4. Failure Modes & Diagnostics (RCA Triage Cheatsheet)

| Symptom Category | Potential Root Cause | Source File / Class | Diagnostic Action |
| :--- | :--- | :--- | :--- |
| **Native Heap OOM / Crash** | **JNI/C++ Memory Leak**: FICO Xpress objects (`XPRS`, `XPRB`) allocated in `runModel` never released. | `OptModel.java` | Check Native Heap metrics; Inspect `OptModel` lifecycle; Verify `finally` block absence. |
| **Socket Exhaustion / Hangs** | **HTTP Connection Leak**: `HttpURLConnection` opened in `connectToFOS` not closed on exception path. | `LegDataRepositoryImpl.java` | Monitor `ESTABLISHED` socket count; Check for `IOException` spikes in logs. |
| **Latency Spikes / GC Thrashing** | **Allocation Churn**: `deepCopy` of `DutyInfo` inside nested loops in pairing logic. | `ShortestPathComponent.java` | Analyze GC logs (Young Gen); Check CPU usage during `identifyDhdFromBase` calls. |
| **Data Corruption / Race Conditions** | **Mutable State Hazard**: `PilotRedeyeRule` modifies shared `UnsequencedLegPairing` state during iteration. | `PilotRedeyeRule.java` | Reproduce concurrent runs; Check for inconsistent `redeye` flags in output. |
| **Connection Pool Saturation** | **Azure Client Leak**: New `BlobClient` created per upload in `saveData` loop without pooling. | `AzureBlobRepositoryImpl.java` | Monitor Azure SDK connection counts; Check for `BlobStorageException` timeouts. |
| **CPU Overutilization** | **Inefficient Algo**: O(N) linear scan in `FSOUtil.daysBetween` instead of O(1). | `FSOUtil.java` | Profile CPU hotspots; Check date range calculations in `QLAProcessor`. |
| **Out of Memory (Heap)** | **State Bloat**: Indefinite growth of `labelsMap`/`dhdHM` without TTL/Eviction. | `ShortestPathComponent.java` | Monitor Heap usage trends; Check dataset size vs. map capacity. |

**Immediate RCA Focus**:
1.  **Verify Native Memory**: Is `OptModel` closing FICO resources? (Critical)
2.  **Check Socket Counts**: Are `HttpURLConnection` instances accumulating? (Critical)
3.  **Review Concurrency**: Are `PilotRedeyeRule` mutations causing race conditions? (High)