# RCA Context Prompt: Sequence_Builder Incident Observer

## 1. System Blueprint & Tech Stack
*   **Core Runtime**: Spring Boot 3.x (Java), `SequenceBuilderApplication` entry point.
*   **Architecture**: Layered Microservice (Controller -> Service -> Repository). Async event-driven via Kafka.
*   **Key Components**:
    *   **Ingestion**: `KafkaConsumerService` (Topic: `${solver.topic.name}`, Concurrency: `${sb.consumer.topics.concurrency}`).
    *   **Logic**: `HttpSolverController` (HTTP), `SequenceBuilder` (Solver Engine), `RunStateManager` (Thread-safe state).
    *   **Rules**: `PilotRedeyeRule`, `ThreeAMHBT`, `FARedeyeRule` (Aviation Regulatory Logic).
    *   **Persistence**: `LegDataRepositoryImpl` (External FOS API), `AzureBlobRepositoryImpl` (Blob Storage).
    *   **Serialization**: Jackson (`ObjectMapper`), Custom `LocalDateDeserializer`.
    *   **Compression**: `CompressUtil` (Byte array compression for solver outputs).
    *   **Observability**: `TeamsNotification` (Webhooks), Swagger/OpenAPI v3.
*   **Scale**: 208 files, 196 classes, 710 methods. High-throughput, event-driven.

## 2. Architectural Advantages & Safeguards
*   **Fault Tolerance**: Manual Kafka Acknowledgment (`Acknowledgment` interface) enforces exactly-once processing semantics.
*   **Concurrency Control**: `RunStateManager` manages transient state (SnapshotId, Kill flags) with thread-safe transitions.
*   **Decoupling**: Kafka abstraction separates business logic from infrastructure; `KafkaProducerConfig` and `KafkaConsumerService` isolate messaging concerns.
*   **Validation**: Custom JSON deserializers enforce strict temporal constraints on flight data.
*   **Resilience**: `@EnableScheduling` supports background tasks; Spring IoC manages bean lifecycles.
*   **Visibility**: Real-time status via `/run/status` and critical alerts via Microsoft Teams webhooks.

## 3. Architectural Limitations
*   **Resource Leaks**: `HttpURLConnection` in `LegDataRepositoryImpl.connectToFOS` lacks guaranteed `disconnect()` in all paths (risk of socket exhaustion).
*   **Memory Churn**: `DutyInfo::deepCopy` called in tight loops (`ShortestPathComponent`) creates massive GC pressure.
*   **Concurrency Hazards**: `PilotRedeyeRule` mutates shared `UnsequencedLegPairing` objects during validation (race conditions/corruption).
*   **Algorithmic Efficiency**: `FSOUtil.daysBetween` uses O(N) linear scan instead of O(1) `ChronoUnit`.
*   **Global State**: `FSOUtil` uses static setters for tokens (`setAccessTokenDto`), breaking thread-safety and horizontal scaling.
*   **Connection Pooling**: `AzureBlobRepositoryImpl` instantiates `BlobClient` per write operation (no pooling).
*   **State Bloat**: Lack of explicit TTL/cleanup for large in-memory maps (e.g., `dhdHM`) risks OOM in long-running processes.
*   **Parallelism Limits**: Constrained by JVM heap tuning and GC pauses; Kafka concurrency is dynamic but limited by consumer thread pool.

## 4. Failure Modes & Diagnostics (RCA Triage Cheatsheet)

| Symptom | Probable Root Cause | Source File / Method | Diagnostic Action |
| :--- | :--- | :--- | :--- |
| **Socket Exhaustion / `Too many open files`** | `HttpURLConnection` leak in `connectToFOS` | `LegDataRepositoryImpl.java` (L1-45) | Check OS file descriptors; verify `finally` block logic. |
| **High CPU / Frequent Full GC / Stalls** | Massive `deepCopy` churn in `identifyDhdFromBase` | `ShortestPathComponent.java` (L145-165) | Monitor GC logs; check heap dump for `DutyInfo` instances. |
| **Non-Deterministic Results / Logic Errors** | Shared object mutation in `checkRedeyeDuty` | `PilotRedeyeRule.java` (L15-35) | Inspect `UnsequencedLegPairing` state consistency across threads. |
| **Latency Spikes in Date Checks** | O(N) loop in `daysBetween` | `FSOUtil.java` (L105-115) | Profile CPU usage on date calculation paths. |
| **Auth Failures / Data Leakage** | Static token overwrites in multi-threaded env | `FSOUtil.java` (L120-130) | Trace `accessTokenDto` assignment timing vs. request flow. |
| **High Write Latency / GC Pressure** | Per-request `BlobClient` instantiation | `AzureBlobRepositoryImpl.java` (L10-25) | Check `BlobClient` creation frequency in logs. |
| **OOM Kill (Long Running)** | Unbounded in-memory map growth (`dhdHM`) | `RunStateManager` / Solver Logic | Check memory usage trends; verify no TTL on caches. |
| **Duplicate Solver Executions** | Kafka Ack failure or Consumer Offset drift | `KafkaConsumerService.java` (L42) | Verify `Acknowledgment` commit success rate. |
| **Connection Timeouts** | External FOS API unavailability | `LegDataRepositoryImpl.java` | Check external API health and network connectivity. |

**Immediate RCA Directive**: Prioritize checking `LegDataRepositoryImpl` for socket leaks and `ShortestPathComponent` for memory spikes if CPU/Memory metrics correlate with solver throughput.