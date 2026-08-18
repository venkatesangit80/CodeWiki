# SRE & Performance Audit Report: Sequence Builder Solver

## 1. SRE Vulnerability Summary

*   **Critical Resource Leak:** `HttpURLConnection` instances are instantiated inside `LegDataRepositoryImpl.connectToFOS` without guaranteed closure in all exception paths, risking socket exhaustion under load.
*   **Native Memory Leak Risk:** `OptModel` initializes FICO Xpress native objects (`XPRS`, `XPRB`) in `runModel` but lacks explicit `close()` or `dispose()` calls in a `finally` block, potentially leaking native heap memory across multiple optimization runs.
*   **High GC Pressure:** Excessive `DutyInfo::deepCopy` operations occur inside tight loops in `ShortestPathComponent.identifyDhdFromBase` and `identifyDhdToBase`, creating significant garbage generation during pairing generation.
*   **Concurrency Hazard:** Validation rules (e.g., `PilotRedeyeRule`, `BaseLayover`) mutate shared `UnsequencedLegPairing` objects (setting `redeye` flags) during iteration, risking race conditions if the same pairing instance is processed concurrently or reused.
*   **Inefficient Data Structures:** `FSOUtil.daysBetween` implements an O(N) linear scan using `plusDays` in a loop instead of utilizing `ChronoUnit.DAYS.between` for O(1) calculation.
*   **Missing State TTL:** While not a Flink job, the codebase relies heavily on in-memory `Map` structures (`labelsMap`, `dhdHM`) that grow indefinitely without eviction policies, risking OutOfMemory errors on large datasets.
*   **Azure Client Instantiation:** `BlobClient` is instantiated inside the `saveData` loop in `AzureBlobRepositoryImpl`, preventing connection pooling and increasing latency.

---

## 2. Detailed Vulnerability Analysis

### 2.1 Connection & Resource Leaks
**Severity:** Critical
**Impact:** Socket exhaustion, `OutOfMemoryError`, application hangs.

The `LegDataRepositoryImpl.connectToFOS` method creates a new `HttpURLConnection` for every script execution. While `try-with-resources` is used for streams, the `HttpURLConnection` itself is not explicitly closed in the `catch` blocks or if an exception occurs before the `try` block completes its scope properly. If the pool of connections is exhausted, subsequent requests will fail.

**File:** `src/main/java/com/aa/fso/repository/LegDataRepositoryImpl.java`
**Lines:** [L1-L45] (approximate based on snippet)

```java
public  String connectToFOS(String script) throws IOException {
    StringBuilder response = new StringBuilder();
    try {
        URL FosUpdate = new URL("https://tapi.adt.aa.com/Service.svc");
        HttpURLConnection conn = (HttpURLConnection) FosUpdate.openConnection();
        // ... setup headers ...
        
        // Stream handling is okay, but conn.close() is missing in finally
        try (OutputStream os = conn.getOutputStream()) { ... }
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()))) { ... }
        
    } catch (Exception e) {
        e.printStackTrace();
        // Connection leak here if exception occurs before streams are closed
    }
    return response.toString();
}
```

**Recommendation:** Wrap the entire logic in a `try-with-resources` block ensuring `HttpURLConnection` is closed, or explicitly call `conn.disconnect()` in a `finally` block.

### 2.2 Native JNI C++ Memory Leaks
**Severity:** Critical
**Impact:** Native heap exhaustion, eventual crash of the JVM process.

The `OptModel` class interacts with the FICO Xpress Optimizer (C++ library). The `runModel` method initializes the solver environment and problem instances. However, there is no corresponding cleanup logic to free these native resources after the optimization completes. In a long-running service processing multiple snapshots, native memory will accumulate until the OS kills the process.

**File:** `src/main/java/com/aa/fso/optmodel/OptModel.java`
**Lines:** [L1-L50] (approximate based on snippet)

```java
public void runModel(RunStateManager runStateManager) throws KillRunException {
    // ... model initialization happens in initialize() ...
    model.getXPRSprob().setDblControl(...);
    model.mipOptimize("d");
    
    // ... parsing solution ...
    
    // NO CLEANUP: model.dispose() or similar native cleanup is missing
    // If this method is called repeatedly, native memory leaks.
}
```

**Recommendation:** Implement a `close()` or `dispose()` method in `OptModel` that calls the native library's cleanup functions. Ensure this is called in a `finally` block in the service layer after `runModel` completes.

### 2.3 High Memory Allocation Churn & GC Pressure
**Severity:** High
**Impact:** Increased GC frequency, latency spikes, reduced throughput.

Inside `identifyDhdFromBase` and `identifyDhdToBase`, a new `UnsequencedLegPairing` and a deep copy of the entire `DutyInfo` list are created for *every* potential deadhead leg checked. This happens inside nested loops iterating over dates and flight legs.

**File:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
**Lines:** [L145-L165] (approximate based on snippet)

```java
for (int f = flightLegs.size() - 1; f >= 0; f--) {
    UnsequencedLeg flightLeg = flightLegs.get(f);

    // CRITICAL: Deep copying the entire duty list for every candidate leg
    UnsequencedLegPairing tempPairing = new UnsequencedLegPairing(pairing);
    tempPairing.setFlightDutyPeriods(pairing.getFlightDutyPeriods().stream()
            .map(DutyInfo::deepCopy) // Expensive operation
            .collect(Collectors.toList()));
            
    // ... logic ...
}
```

**Recommendation:**
1.  **Lazy Evaluation:** Avoid deep copying unless the legality check actually requires modification. Pass the original object and a "delta" or "context" object to the validator.
2.  **Object Pooling:** If deep copies are unavoidable, consider an object pool for `DutyInfo` and `UnsequencedLegPairing` to reduce allocation overhead.
3.  **Early Exit:** Move expensive checks (like `isDhdLegal`) earlier in the loop if possible to avoid unnecessary cloning.

### 2.4 Concurrency Hazards / Shared Object Mutation
**Severity:** High
**Impact:** Data corruption, incorrect legality results, race conditions.

Validation rules like `PilotRedeyeRule` and `BaseLayover` modify the state of the input `UnsequencedLegPairing` object (e.g., setting `redeye` flags) during the validation process. If the same `pairing` instance is passed to multiple threads or reused in a subsequent operation before the validation is complete, the state will be corrupted.

**File:** `src/main/java/com/aa/fso/contractualrules/PilotRedeyeRule.java`
**Lines:** [L15-L30] (approximate based on snippet)

```java
private boolean checkRedeyeDuty(UnsequencedLegPairing sequenceInfo, Map<String, Integer> hashMap) {
    // MUTATION: Modifying the input object's state
    if(sequenceInfo.getRedeye() != null) {
         sequenceInfo.setRedeye(null); // Resetting state
    }
    // ...
    for (DutyInfo dutyPeriod : dutyPeriods) {
        // ...
        dutyPeriod.setRedeye(true); // Mutating child object
        sequenceInfo.setRedeye(true); // Mutating parent object
    }
    return redeye;
}
```

**Recommendation:**
1.  **Immutable Validation:** Refactor validation rules to accept a copy of the object or return a result object containing the calculated flags rather than mutating the input.
2.  **Thread Safety:** If the input objects are immutable, this is safe. If they are mutable and shared, ensure strict single-threaded access or synchronize access.

### 2.5 Inefficient Data Structures
**Severity:** Medium
**Impact:** CPU waste, slower execution time.

The `daysBetween` utility method calculates the difference between two dates using a `while` loop incrementing by one day. This is O(N) where N is the number of days. For a 7-day window, it's negligible, but for larger ranges or high-frequency calls, it is inefficient.

**File:** `src/main/java/com/aa/fso/util/FSOUtil.java`
**Lines:** [L1-L10] (approximate based on snippet)

```java
public static int daysBetween(LocalDateTime startDateTime, LocalDateTime endDateTime) {
    LocalDate startDate = startDateTime.toLocalDate();
    LocalDate endDate = endDateTime.toLocalDate();

    int days = 0;
    while (startDate.isBefore(endDate) && !startDate.equals(endDate)) {
      days++;
      startDate = startDate.plusDays(1); // Linear scan
    }
    days++;
    return days;
}
```

**Recommendation:** Replace with `ChronoUnit.DAYS.between(startDateTime.toLocalDate(), endDateTime.toLocalDate())`.

### 2.6 Azure Blob Client Leaks
**Severity:** Medium
**Impact:** Latency increase, connection pool exhaustion.

In `AzureBlobRepositoryImpl.saveData`, a new `BlobClient` is built and used inside the method. While the `try-with-resources` block closes the stream, the `BlobClient` itself might hold underlying connections that are not pooled efficiently if created frequently.

**File:** `src/main/java/com/aa/fso/repository/AzureBlobRepositoryImpl.java`
**Lines:** [L15-L25] (approximate based on snippet)

```java
try (ByteArrayInputStream dataStream = new ByteArrayInputStream(dataBytes)) {
    BlobClient blobClient = currentEnvClientBuilder.blobName(folderName + "/" + fileName + fileExtension).buildClient();
    blobClient.upload(dataStream, dataBytes.length, true);
    // blobClient is not explicitly closed, though it might be disposable
}
```

**Recommendation:** Ensure `BlobClient` implements `AutoCloseable` (it does in newer SDKs) and wrap it in `try-with-resources`, or better yet, reuse a singleton `BlobContainerClient` and create `BlobClient` instances only for specific blobs if necessary, or rely on the SDK's internal pooling if available.

---

## 3. Actionable Remediations & Best Practices

### Immediate Actions (P0)
1.  **Fix Resource Leaks:** Refactor `LegDataRepositoryImpl.connectToFOS` to ensure `HttpURLConnection.disconnect()` is called in a `finally` block.
2.  **Native Cleanup:** Add a `close()` method to `OptModel` that calls `model.close()` (or equivalent FICO API) and invoke it in `SolverService.runSolver` within a `finally` block.
3.  **Reduce GC Pressure:** Refactor `identifyDhdFromBase` to avoid `deepCopy` inside the innermost loop. Consider passing a "modification context" to the validation logic instead of cloning the whole object.

### Short Term (P1)
4.  **Refactor Date Calculation:** Replace `FSOUtil.daysBetween` with `ChronoUnit.DAYS.between`.
5.  **Immutable Validation:** Refactor `PilotRedeyeRule` and similar classes to return a `ValidationResult` object instead of mutating the `UnsequencedLegPairing`.
6.  **Azure Client Management:** Ensure `BlobClient` is properly disposed of or refactor to use a reusable `BlobContainerClient` pattern.

### Long Term (P2)
7.  **State Management:** If this code is part of a larger streaming pipeline (Flink), ensure state descriptors are configured with `enableTimeToLive()` to prevent state bloat.
8.  **Connection Pooling:** Replace raw `HttpURLConnection` usage with `HttpClient` (Java 11+) or Apache HttpClient which supports connection pooling natively.
9.  **Monitoring:** Add metrics for:
    *   Native memory usage (via JMX or native hooks).
    *   GC pause times.
    *   Number of `HttpURLConnection` creations vs. successful completions.
    *   Number of `OptModel` instantiations.

### Configuration Recommendations
*   **JVM Flags:** Increase `-XX:+UseG1GC` and tune `-XX:MaxGCPauseMillis` to handle the high allocation churn identified.
*   **Kubernetes Resources:** Based on the audit, the current 32Gi/8CPU (nonprod) or 64Gi/8CPU (prod) limits seem appropriate given the heavy computation, but ensure `memoryRequest` is set high enough to avoid OOMKills during peak GC events.
*   **Timeouts:** Set explicit timeouts on `HttpURLConnection` and Azure SDK calls to prevent hanging threads.