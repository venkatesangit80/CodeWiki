# SRE & Performance Audit Report: Sequence Builder Solver

## 1. SRE Vulnerability Summary

*   **Critical Resource Leak:** `HttpURLConnection` instances are instantiated inside `LegDataRepositoryImpl.connectToFOS` without guaranteed closure in `finally` blocks, risking socket exhaustion under high load.
*   **Native Memory Leak Risk:** `OptModel` (FICO Xpress) initializes native C++ optimizer instances (`XPRS`, `XPRB`) inside the `optimize` method but lacks explicit `dispose()` or `close()` calls in a `finally` block, leading to native heap accumulation.
*   **High GC Pressure:** Aggressive use of `DutyInfo::deepCopy` inside tight loops (`identifyDhdFromBase`, `identifyDhdToBase`, `updateDutyInfoList`) creates massive object churn, likely triggering frequent Full GCs.
*   **Concurrency Hazard:** Validation rules (e.g., `PilotRedeyeRule`, `BaseLayover`) mutate shared input objects (`UnsequencedLegPairing`, `DutyInfo`) directly (e.g., `setRedeye`, `setFlightsWithInDuty`), causing race conditions if pairings are reused or cached.
*   **Inefficient Data Structures:** `FSOUtil.daysBetween` implements an O(N) linear scan using `plusDays` instead of utilizing `ChronoUnit.DAYS.between` for O(1) calculation.
*   **Missing State TTL:** While not a Flink job, the codebase lacks explicit state cleanup mechanisms for large in-memory maps (`labelsMap`, `dhdHM`) which could grow indefinitely without bounds checking.
*   **Azure Client Instantiation:** `BlobClient` is created inside the `saveData` loop in `AzureBlobRepositoryImpl`, preventing connection pooling and increasing latency.

---

## 2. Detailed Vulnerability Analysis

### 2.1 Connection & Resource Leaks
**Severity:** Critical
**Impact:** Socket exhaustion, `OutOfMemoryError` (direct buffers), Service Unavailability.

The `LegDataRepositoryImpl.connectToFOS` method opens an `HttpURLConnection` but relies on `try-with-resources` only for the inner streams (`OutputStream`, `BufferedReader`). If an exception occurs before entering the inner `try` blocks, or if the outer `try` block fails, the connection itself may not be closed.

*   **File:** `src/main/java/com/aa/fso/repository/LegDataRepositoryImpl.java`
*   **Lines:** `L1-L45` (approximate based on snippet)
*   **Snippet:**
    ```java
    public String connectToFOS(String script) throws IOException {
        StringBuilder response = new StringBuilder();
        try {
            URL FosUpdate = new URL("https://tapi.adt.aa.com/Service.svc");
            HttpURLConnection conn = (HttpURLConnection) FosUpdate.openConnection();
            // ... setup ...
            try (OutputStream os = conn.getOutputStream()) { // Stream closed, but conn might not be
                os.write(script.getBytes());
                // ...
            }
            // ...
        } catch (Exception e) {
            e.printStackTrace();
            // Connection 'conn' is leaked here if exception happens before try-with-resources
        }
        return response.toString();
    }
    ```

**Recommendation:** Wrap the entire connection logic in a `try-with-resources` block or ensure `conn.disconnect()` is called in a `finally` block.

### 2.2 Native JNI C++ Memory Leaks
**Severity:** Critical
**Impact:** Native Heap Overflow, Application Crash (OOM), System Instability.

The `OptModel` class interacts with the FICO Xpress Optimizer. The `runModel` method accesses native objects (`model.getXPRSprob()`, `model.mipOptimize()`). There is no evidence of a `close()`, `dispose()`, or `delete` call for the native model instance after the optimization completes. If this service runs continuously or processes multiple snapshots sequentially without restarting, native memory will leak.

*   **File:** `src/main/java/com/aa/fso/optmodel/OptModel.java`
*   **Lines:** `L1-L60` (approximate)
*   **Snippet:**
    ```java
    public void runModel(RunStateManager runStateManager) throws KillRunException {
        model.getXPRSprob().setDblControl(XPRS.MIPTOL, ModelParams.C_MIPTOLERANCE);
        // ...
        model.mipOptimize("d");
        // ...
        // NO CLEANUP HERE
    }
    ```
    *Note: The `OptModel` constructor likely initializes the native environment. Without a corresponding destructor or explicit close method called after `parseSolution`, the native heap grows.*

**Recommendation:** Implement a `close()` method in `OptModel` that calls the native Xpress cleanup routines and invoke it in a `finally` block within `OptimizationServiceImpl.optimize`.

### 2.3 High Memory Allocation Churn & GC Pressure
**Severity:** High
**Impact:** High Latency, Frequent Full GCs, Throughput degradation.

The code performs deep cloning of complex objects (`DutyInfo`) inside nested loops used for generating candidate pairings. This is particularly evident in `identifyDhdFromBase` and `identifyDhdToBase` where a temporary pairing is created for every potential deadhead leg check.

*   **File:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
*   **Lines:** `L230-245` (inside `identifyDhdFromBase`)
*   **Snippet:**
    ```java
    for (int f = flightLegs.size() - 1; f >= 0; f--) {
        UnsequencedLeg flightLeg = flightLegs.get(f);
        // CRITICAL: Creates a new Pairing and Deep Copies entire DutyInfoList for EVERY iteration
        UnsequencedLegPairing tempPairing = new UnsequencedLegPairing(pairing);
        tempPairing.setFlightDutyPeriods(pairing.getFlightDutyPeriods().stream()
                .map(DutyInfo::deepCopy) // Expensive operation
                .collect(Collectors.toList()));
        
        // ... logic ...
        if (isDhdLegal(...)) {
            // ...
            return;
        }
    }
    ```
    *Context:* If `flightLegs` contains 100 items and `pairing` has 5 duties, this creates 500+ `DutyInfo` clones per loop iteration.

**Recommendation:**
1.  Avoid deep copying if possible. Pass a copy-only-on-modification strategy.
2.  If deep copy is required, reuse a single `tempPairing` object and manually reset fields instead of creating a new instance every loop.
3.  Profile the `deepCopy` implementation to ensure it isn't doing unnecessary work.

### 2.4 Concurrency Hazards / Shared Object Mutation
**Severity:** High
**Impact:** Data Corruption, Incorrect Legalities, Race Conditions.

Validation rules are designed to be stateless but are mutating the input `UnsequencedLegPairing` and its internal `DutyInfo` objects. Since these pairings are often part of a larger solution space or cached, mutating them during validation causes side effects.

*   **File:** `src/main/java/com/aa/fso/contractualrules/PilotRedeyeRule.java`
*   **Lines:** `L15-L30` (inside `checkRedeyeDuty`)
*   **Snippet:**
    ```java
    private boolean checkRedeyeDuty(UnsequencedLegPairing sequenceInfo, Map<String, Integer> hashMap) {
        // MUTATION: Setting state on the input object
        if(sequenceInfo.getRedeye() != null) {
             sequenceInfo.setRedeye(null); // Clearing state
        }
        // ...
        for (DutyInfo dutyPeriod : dutyPeriods) {
            // MUTATION: Modifying the duty object passed in
            dutyPeriod.setRedeye(true); // Side effect!
            sequenceInfo.setRedeye(true);
        }
        return redeye;
    }
    ```
*   **File:** `src/main/java/com/aa/fso/contractualrules/BaseLayover.java`
*   **Lines:** `L15-L25`
*   **Snippet:**
    ```java
    // MUTATION: Modifying the list directly
    List<Node> flights = dutyPeriod.getFlightsWithInDuty();
    // ... logic ...
    // If this method is called on a shared object, the list is modified.
    ```

**Recommendation:**
1.  **Immutable Validation:** Validation methods should accept immutable copies or read-only views.
2.  **Separate State:** Store validation results (e.g., `isRedeye`) in a separate metadata map or a wrapper object, not on the domain entity itself.
3.  **Defensive Copying:** If mutation is unavoidable for performance, ensure the caller knows they are receiving a mutated object, or clone the object *before* passing it to the validator.

### 2.5 Inefficient Data Structures
**Severity:** Medium
**Impact:** CPU Waste, Increased Latency.

The `daysBetween` utility method uses a `while` loop to increment days one by one. For large date ranges, this is significantly slower than the built-in `ChronoUnit` API.

*   **File:** `src/main/java/com/aa/fso/util/FSOUtil.java`
*   **Lines:** `L100-L110`
*   **Snippet:**
    ```java
    public static int daysBetween(LocalDateTime startDateTime, LocalDateTime endDateTime) {
        LocalDate startDate = startDateTime.toLocalDate();
        LocalDate endDate = endDateTime.toLocalDate();
        int days = 0;
        // O(N) Linear Scan
        while (startDate.isBefore(endDate) && !startDate.equals(endDate)) {
          days++;
          startDate = startDate.plusDays(1); // Expensive operation in loop
        }
        days++;
        return days;
    }
    ```

**Recommendation:** Replace with `ChronoUnit.DAYS.between(startDateTime.toLocalDate(), endDateTime.toLocalDate())`.

### 2.6 Connection & Resource Leaks (Azure)
**Severity:** Medium
**Impact:** Latency, Connection Pool Exhaustion.

`AzureBlobRepositoryImpl.saveData` creates a new `BlobClient` for every single upload operation. This prevents connection reuse and increases the overhead of establishing connections to Azure.

*   **File:** `src/main/java/com/aa/fso/repository/AzureBlobRepositoryImpl.java`
*   **Lines:** `L15-L25`
*   **Snippet:**
    ```java
    public boolean saveData(...) {
        // ...
        try (ByteArrayInputStream dataStream = new ByteArrayInputStream(dataBytes)) {
            // NEW CLIENT CREATED EVERY TIME
            BlobClient blobClient = currentEnvClientBuilder.blobName(...).buildClient();
            blobClient.upload(dataStream, dataBytes.length, true);
        }
        // ...
    }
    ```

**Recommendation:** Instantiate `BlobClient` once (e.g., in the constructor or as a singleton) and reuse it, or use `BlobContainerClient` to create clients efficiently.

---

## 3. Actionable Remediations & Best Practices

### Immediate Actions (P0)
1.  **Fix Resource Leaks:** Refactor `LegDataRepositoryImpl.connectToFOS` to ensure `HttpURLConnection.disconnect()` is called in a `finally` block.
    ```java
    HttpURLConnection conn = null;
    try {
        // ... setup
        conn = (HttpURLConnection) url.openConnection();
        // ...
    } finally {
        if (conn != null) conn.disconnect();
    }
    ```
2.  **Native Cleanup:** Add a `close()` method to `OptModel` that calls the FICO Xpress native cleanup functions. Ensure `OptimizationServiceImpl.optimize` wraps the `optModel` usage in a `try-finally` block to call `optModel.close()`.
3.  **Stop Object Churn:** Refactor `identifyDhdFromBase` and `identifyDhdToBase`. Instead of `new UnsequencedLegPairing(pairing)` and `deepCopy`, create a single reusable `tempPairing` instance and manually revert changes after the legality check, or pass a "copy-on-write" flag to the validation logic.

### Short Term (P1)
4.  **Fix Date Calculation:** Replace `FSOUtil.daysBetween` with `ChronoUnit.DAYS.between`.
5.  **Azure Client Reuse:** Move `BlobClient` instantiation out of the `saveData` method. Cache the client in the repository class.
6.  **Validation Isolation:** Refactor `PilotRedeyeRule` and similar classes to return a result object (e.g., `ValidationResult`) instead of mutating the `UnsequencedLegPairing`. This ensures thread safety if the solver runs in parallel threads.

### Long Term (P2)
7.  **State Management:** If this application is eventually migrated to Flink or a similar streaming engine, ensure all `StateDescriptor` usage includes `enableTimeToLive()` to prevent state bloat.
8.  **Profiling:** Implement JFR (Java Flight Recorder) or async-profiler in the staging environment to capture GC logs and CPU profiles. Verify if the `deepCopy` operations are indeed the primary cause of GC pressure.
9.  **Connection Pooling:** If `connectToFOS` is called frequently, consider using Apache HttpClient or OkHttp with a connection pool instead of `HttpURLConnection`.

### Configuration Review
*   **Kubernetes Resources:** The `k8s/IT/eastus-qa/kustomization.yaml` sets memory limits to `64G`. Given the identified memory leaks (Native + Java Churn), ensure the JVM Heap is tuned (`-Xmx`) to be slightly less than the container limit (e.g., 50G) to leave room for native memory and off-heap buffers.
*   **Timeouts:** Ensure `HttpURLConnection` timeouts are explicitly set to prevent hanging threads if the FOS service is slow.