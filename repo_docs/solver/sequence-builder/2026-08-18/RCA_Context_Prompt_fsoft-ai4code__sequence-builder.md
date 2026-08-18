```markdown
# RCA Context Prompt: Sequence Builder Incident Observer

## 1. System Blueprint & Tech Stack
- **Core Runtime**: Spring Boot Monolith (`SequenceBuilderApplication`), Java 17+ (implied).
- **Ingestion**: Apache Kafka Consumer (`KafkaConsumerService`), Topic: `${solver.topic.name}`, Concurrency: `${sb.consumer.topics.concurrency}`.
- **Processing**: 
  - Solver Engine: `OptimizationService` + `ShortestPathComponent`.
  - Rules: Custom Rule Engine (`FAR117FTRule`, `PilotRedeyeRule`, `BaseLayover`).
  - Models: `FlightLeg`, `DutyInfo`, `UnsequencedLegPairing`.
- **Persistence**: Spring Data JPA (`LegDataRepositoryImpl`, `OutputDataRepository`), Azure Blob Storage (`AzureBlobRepositoryImpl`).
- **External**: HTTP (FOS Update), Auth (PingFederate/Access Tokens), Notifications (MS Teams).
- **Key Artifacts**: 
  - `HttpSolverController` (API Entry), `KillController` (Lifecycle), `LegDataRepositoryImpl` (DB/HTTP), `FSOUtil` (Utils).

## 2. Architectural Advantages & Safeguards
- **Decoupling**: Kafka-based async processing isolates API latency from solver compute time.
- **Resilience**: `KillController` exposes `/run/status` and `/kill` endpoints for manual intervention.
- **Validation**: `TeamsNotification` triggers on `KillRunException` for immediate ops visibility.
- **Serialization**: Jackson `ObjectMapper` handles robust JSON binding for `UserInput`/`SolverResponseDTO`.
- **Modularity**: Lombok reduces boilerplate; distinct separation of Controllers, Services, and Repositories.

## 3. Architectural Limitations
- **Resource Exhaustion Risk**: 
  - `HttpURLConnection` in `LegDataRepositoryImpl` lacks `disconnect()` in hot paths.
  - `BlobClient` instantiated per-call in `AzureBlobRepositoryImpl` without pooling.
- **GC Pressure**: Aggressive `DutyInfo::deepCopy` inside `ShortestPathComponent` loops causes high memory churn.
- **Concurrency Flaws**: 
  - Validation rules (`PilotRedeyeRule`) mutate shared input objects (`UnsequencedLegPairing`).
  - Static state (`FSOUtil.accessTokenDto`) risks cross-request contamination.
- **Algorithmic Latency**: `FSOUtil.daysBetween` uses $O(N)$ loop instead of $O(1)$ `ChronoUnit`.
- **State Management**: No explicit TTL enforcement for stateful operations (critical if migrating to Flink).

## 4. Failure Modes & Diagnostics (RCA Triage Cheatsheet)

| Symptom | Probable Root Cause | Source Artifact | Diagnostic Action |
| :--- | :--- | :--- | :--- |
| **Socket Exhaustion / `Too many open files`** | `HttpURLConnection` leak in `connectToFOS` | `LegDataRepositoryImpl.java` | Check `conn.disconnect()` calls; monitor file descriptors. |
| **Connection Pool Saturation / Timeout** | Dynamic `BlobClient` creation in `saveData` | `AzureBlobRepositoryImpl.java` | Verify connection reuse; check `BlobClient` lifecycle. |
| **High CPU / GC Pauses / OOM** | `DutyInfo::deepCopy` in tight loops | `ShortestPathComponent.java` | Profile heap; look for `identifyDhdFromBase`/`updateDutyInfoList` spikes. |
| **Data Corruption / Race Conditions** | Mutation of shared `UnsequencedLegPairing` | `PilotRedeyeRule.java` | Inspect `setRedeye(true)` calls; check thread affinity. |
| **Incorrect Token / Tenant Leakage** | Static field mutation in `FSOUtil` | `FSOUtil.java` | Check `accessTokenDto`/`pingFederateToken` scope; verify request isolation. |
| **Solver Latency Spikes (Long Durations)** | $O(N)$ date calculation loop | `FSOUtil.java` (`daysBetween`) | Replace loop with `ChronoUnit.DAYS.between`. |
| **Unbounded State Growth (Flink Migration)** | Missing TTL on State Descriptors | N/A (Future) | Enforce `.enableTimeToLive()` on all `ValueStateDescriptor`. |
| **Silent Failures / No Alerts** | `KillRunException` not caught or logged | `KafkaConsumerService.java` | Verify exception handling chain and `TeamsNotification` trigger. |
| **Stale Data / Incorrect Schedules** | `LegDataRepositoryImpl` caching issues | `LegDataRepositoryImpl.java` | Validate query freshness and `FosUpdate` sync logic. |
| **HTTP 500 on `/solveDebug`** | `HttpURLConnection` leak or DB timeout | `HttpSolverController.java` | Trace request ID; check `LegDataRepository` logs. |
| **Memory Leak (Gradual)** | `BlobClient` not closed in `saveData` | `AzureBlobRepositoryImpl.java` | Monitor `BlobClient` instance count vs. GC. |
```