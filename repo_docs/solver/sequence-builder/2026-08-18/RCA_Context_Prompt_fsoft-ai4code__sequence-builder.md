# RCA Context Prompt: Sequence Builder Incident Observer

## 1. System Blueprint & Tech Stack
*   **Core Runtime**: Spring Boot 3.x (Embedded Tomcat, Actuator, Auto-config).
*   **Entry Point**: `SequenceBuilderApplication` (Scheduling enabled).
*   **Ingestion**: Apache Kafka (`solver.topic.name`), Manual Ack (`Acknowledgment ack`), Exactly-Once Semantics.
*   **Orchestration**: `KafkaConsumerService` (Concurrency: `${sb.consumer.topics.concurrency}`).
*   **Logic Engine**: `SolverService` + Rule Engines (`FAR117RestTimeRule`, QLA).
*   **Persistence**:
    *   Relational: Spring Data JPA (`LegDataRepository`, `InputDataRepositoryImpl`).
    *   Object Storage: Azure Blob Storage (`AzureBlobController`, `AzureBlobRepositoryImpl`).
*   **Data Flow**: Kafka Consumer → Validation (`InputValidationProcessor`) → Solver → Compression (`CompressUtil`) → Kafka Producer.
*   **Key Classes**: `ShortestPathComponent`, `ConstructNetwork`, `RunStateManager`, `JsonUtil`, `LegDataRepositoryImpl`.

## 2. Architectural Advantages & Safeguards
*   **Fault Tolerance**: Manual Kafka ACK ensures message processing completion before offset commit; `try-catch-finally` blocks in consumers prevent consumer group blocking on exceptions.
*   **Observability**: SLF4J/Logback with Trace IDs; Spring Actuator for health checks; Swagger/OpenAPI for contract validation.
*   **Performance**: Async processing model; Binary payload compression (`CompressUtil`) for large JSON solutions; Polyglot offloading for critical parsing.
*   **Isolation**: Separation of Web Layer (REST), Event Layer (Kafka), and Core Logic (Solver) allows independent scaling.
*   **Validation**: Pre-processing via `InputValidationProcessor` to reject malformed payloads early.

## 3. Architectural Limitations
*   **Memory Churn**: Aggressive deep cloning of `DutyInfo`/`UnsequencedLegPairing` in tight loops (`ShortestPathComponent`).
*   **Algorithmic Complexity**: $O(N^2)$ edge construction in `ConstructNetwork.buildNetwork`; $O(L^2)$ path reconstruction via `LinkedList.add(0, ...)`.
*   **Resource Leaks**:
    *   I/O: New `ObjectMapper` instantiation per file write (`JsonUtil`).
    *   Network: Potential socket exhaustion in `LegDataRepositoryImpl.connectToFOS` (missing `disconnect()` in all paths).
*   **State Management**: No TTL/Eviction on in-memory `Map` structures (`labelsMap`, `dhdHM`); risk of OOM on large inputs.
*   **Concurrency**: `RunStateManager` lacks explicit `volatile`/`AtomicBoolean` synchronization; race condition risk on kill signals.
*   **Scalability**: Sequential base processing in `generateSolutionSpace` limits parallel CPU utilization.

## 4. Failure Modes & Diagnostics (RCA Triage Cheatsheet)

| Symptom Category | Probable Root Cause | Source Location | Diagnostic Check |
| :--- | :--- | :--- | :--- |
| **CPU Spikes / Latency** | $O(N^2)$ Graph Construction | `ConstructNetwork.java` [L130-135] | Check `buildNetwork` duration vs. `nodes.size()`. |
| **GC Thrashing / OOM** | Deep Cloning in Loops | `ShortestPathComponent.java` [L145-150] | Monitor Heap usage; Check `identifyDhdFromBase` clone count. |
| **Path Reconstruction Lag** | `LinkedList.add(0, ...)` | `ShortestPathComponent.java` [L45-50] | Check path length ($L$); Look for $O(L^2)$ growth. |
| **Socket Exhaustion** | HTTP Connection Leak | `LegDataRepositoryImpl.java` [L20-45] | Check `connectToFOS` for missing `finally { conn.disconnect() }`. |
| **Serialization Bottleneck** | Repeated `ObjectMapper` Init | `JsonUtil.java` [L10-12] | Check `saveToJsonFile` call frequency vs. CPU usage. |
| **Hang / Non-Termination** | Race Condition on Kill Flag | `RunStateManager.java` | Verify `killRequested` is `volatile` or `AtomicBoolean`. |
| **Out of Memory (Large Runs)** | Indefinite State Growth | `ShortestPathComponent.java` [L1-10] | Check `labelsMap` size; No TTL/Eviction policy found. |
| **Message Stuck / Duplicates** | Manual ACK Failure | `KafkaConsumerService.java` [L42-86] | Verify `ack.acknowledge()` is called only after success. |
| **Input Validation Failures** | Schema Mismatch | `InputValidationProcessor.java` | Check `UserInput` DTO deserialization errors. |

**Immediate Action Protocol**:
1.  **Check Metrics**: Heap usage, GC pause times, Kafka lag, HTTP connection pool status.
2.  **Trace Logs**: Search for `KillRunException`, `InvalidUserInputException`, or `OutOfMemoryError`.
3.  **Verify Code**: Confirm if `RunStateManager` is thread-safe and if `ObjectMapper` is reused.
4.  **Mitigate**: Scale down concurrency (`${sb.consumer.topics.concurrency}`) or enable circuit breakers for FOS API.