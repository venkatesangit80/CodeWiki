```markdown
# RCA Context Prompt: Sequence Builder Incident Observer

## 1. System Blueprint & Tech Stack
- **Core App**: `AAInternal/Sequence_Builder` (Spring Boot 3.x, Java SE).
- **Architecture**: Event-driven, high-throughput. Async processing via **Apache Kafka** (Consumer/Producer).
- **Entry Points**: 
  - REST: `HttpSolverController.solveDebug` (POST), `KillController.getRunStatus`.
  - Async: `KafkaConsumerService` (Topic: `${solver.topic.name}`).
- **Domain Logic**: Flight sequence optimization (FAR 121 compliance). Graph construction (`ConstructNetwork`), Rule Engine (`FAR121RestTimeRule`, `PilotRedeyeRule`).
- **Integrations**: 
  - **DB**: `LegDataRepository` (JPA/Hibernate).
  - **External**: PingFederate (Auth), FICO Xpress (Native C++ Optimizer), Azure Blob Storage.
- **Runtime**: Embedded Tomcat, JVM Heap + Native Heap (JNI).

## 2. Architectural Advantages & Safeguards
- **Fault Tolerance**: `KillRunException` handling triggers `TeamsNotification` and state clearance.
- **Decoupling**: Kafka separation of ingestion (`KafkaConsumerService`) and result publishing (`KafkaProducerService`).
- **Modularity**: 196 classes, 710 methods; clear separation of Controller, Service, Repository, and Rule layers.
- **Config Management**: YAML profiles (`application-itnonprod.yaml`, etc.) for environment-specific Kafka/Timeout tuning.
- **Security**: Filter chain via `SecurityConfig` and `PingFederateTokenClientImpl`.

## 3. Architectural Limitations
- **Native Memory Leaks**: `OptModel` lacks explicit `close()/dispose()` for FICO Xpress native instances (`XPRS`, `XPRB`).
- **Resource Leaks**: 
  - `HttpURLConnection` in `LegDataRepositoryImpl.connectToFOS` not guaranteed closed in all paths.
  - `BlobClient` instantiated per-request in `AzureBlobRepositoryImpl.saveData` (no pooling).
- **Concurrency Hazards**: Mutable state in validation rules (`PilotRedeyeRule`, `BaseLayover`) modifies shared `UnsequencedLegPairing` objects.
- **GC Pressure**: Aggressive `DutyInfo::deepCopy` in tight loops (`identifyDhdFromBase`, `identifyDhdToBase`).
- **Algorithmic Inefficiency**: `FSOUtil.daysBetween` uses O(N) linear scan instead of O(1) `ChronoUnit`.
- **State Bloat**: Large in-memory maps (`labelsMap`, `dhdHM`) lack TTL or eviction policies.

## 4. Failure Modes & Diagnostics (RCA Triage Cheatsheet)

| Symptom | Probable Root Cause | Source File / Component | Diagnostic Action |
| :--- | :--- | :--- | :--- |
| **Native Heap OOM / Crash** | JNI/C++ Memory Leak: `OptModel` fails to dispose native Xpress instances. | `OptModel.java` (No `close()` in `finally`) | Check Native Heap metrics; Inspect `OptimizationServiceImpl` for missing cleanup. |
| **Socket Exhaustion / 503** | `HttpURLConnection` leak in `connectToFOS` (missing `disconnect()`). | `LegDataRepositoryImpl.java` | Monitor open file descriptors; Check for `IOException` in logs during high load. |
| **Azure Latency Spike** | Connection Pool Exhaustion: New `BlobClient` per upload in `saveData`. | `AzureBlobRepositoryImpl.java` | Check Azure connection count; Monitor `saveData` throughput vs. latency. |
| **CPU Spikes / High GC** | Object Churn: `DutyInfo::deepCopy` inside nested loops. | `ShortestPathComponent.java` (`identifyDhd...`) | Analyze GC logs (Full GC frequency); Check CPU usage during `solveDebug`. |
| **Data Corruption / Race** | Mutable State: Rules mutate shared `UnsequencedLegPairing` objects. | `PilotRedeyeRule.java`, `BaseLayover.java` | Check for inconsistent validation results in concurrent runs; Inspect `checkRedeyeDuty`. |
| **Slow Date Calculations** | O(N) Algorithm: `FSOUtil.daysBetween` linear scan. | `FSOUtil.java` | Profile `daysBetween` calls; Compare against `ChronoUnit.DAYS.between`. |
| **Memory Growth (Steady)** | Missing State TTL: Maps (`labelsMap`, `dhdHM`) grow indefinitely. | `SequenceProcessor.java` / Domain Models | Monitor heap growth over time; Check for unbounded map sizes. |

**Immediate RCA Focus**:
1.  **Verify Native Cleanup**: Does `OptModel` release Xpress resources?
2.  **Check Connection Handling**: Are `HttpURLConnection` and `BlobClient` properly closed/reused?
3.  **Validate Concurrency**: Are rules running on shared mutable state?
```