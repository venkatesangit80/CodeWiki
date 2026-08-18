# SRE & Performance Audit Report: Flight Schedule Optimization (FSO) Service

## 1. SRE Vulnerability Summary

*   **Critical Resource Leak:** `HttpURLConnection` instances are instantiated inside `LegDataRepositoryImpl.connectToFOS` without explicit `disconnect()` calls in a `finally` block, risking socket exhaustion under load.
*   **Critical Resource Leak:** `BlobClient` instances are created dynamically inside the `saveData` loop in `AzureBlobRepositoryImpl`, failing to reuse connections or properly dispose of resources, leading to potential connection pool exhaustion.
*   **High Memory Churn:** `DutyInfo::deepCopy` is invoked repeatedly inside tight loops (`identifyDhdFromBase`, `identifyDhdToBase`, `updateDutyInfoList`) creating massive garbage generation during the critical path of pairing generation.
*   **Concurrency Hazard:** Validation rules (e.g., `PilotRedeyeRule`, `BaseLayover`) mutate shared state on input objects (`UnsequencedLegPairing`, `DutyInfo`) via setters like `setRedeye(true)` during read-only validation loops, causing race conditions in multi-threaded environments.
*   **Algorithmic Inefficiency:** `FSOUtil.daysBetween` implements an $O(N)$ linear scan using `plusDays` in a loop instead of utilizing `ChronoUnit.DAYS.between`, causing significant latency for long-duration pairings.
*   **Static State Contamination:** `FSOUtil` contains static fields (`accessTokenDto`, `pingFederateToken`) that are mutated globally, posing a risk of data leakage between concurrent requests or tenant isolation failures.
*   **Missing TTL Configuration:** While no explicit Flink State Descriptors were found in the provided snippets, the architecture implies heavy state usage; if migrated to Flink, `enableTimeToLive()` must be enforced on all state descriptors to prevent unbounded state growth.

---

## 2. Detailed Vulnerability Analysis

### 2.1 Connection & Resource Leaks

**Issue:** The code creates new network connections (`HttpURLConnection`, `BlobClient`) inside processing loops without ensuring they are closed or disconnected. This prevents the underlying connection pools from being reused and can lead to `Too many open files` errors or connection timeouts.

**Evidence:**
*   **File:** `src/main/java/com/aa/fso/repository/LegDataRepositoryImpl.java`
    *   **Location:** `connectToFOS` method [L1-L45]
    *   **Analysis:** `HttpURLConnection` is opened but `conn.disconnect()` is never called. The `try-with-resources` block wraps the `OutputStream` and `BufferedReader`, but not the `HttpURLConnection` itself.
    ```java
    // LEGEND: Missing disconnect()
    HttpURLConnection conn = (HttpURLConnection) FosUpdate.openConnection();
    // ... processing ...
    // No conn.disconnect() here!
    ```

*   **File:** `src/main/java/com/aa/fso/repository/AzureBlobRepositoryImpl.java`
    *   **Location:** `saveData` method [L1-L20]
    *   **Analysis:** A new `BlobClient` is built and used inside the method. While the `try-with-resources` block closes the `dataStream`, the `blobClient` itself is not closed. More critically, if this method is called frequently, it creates a new client instance every time rather than reusing a singleton or pool.
    ```java
    // LEGEND: Dynamic instantiation without reuse/cleanup
    BlobClient blobClient = currentEnvClientBuilder.blobName(...).buildClient();
    blobClient.upload(dataStream, dataBytes.length, true);
    // blobClient is not closed explicitly, though it might be auto-closed by SDK depending on version, 
    // relying on GC is risky for high-throughput scenarios.
    ```

### 2.2 High Memory Allocation Churn & GC Pressure

**Issue:** The algorithm performs deep cloning of complex objects (`DutyInfo`, `UnsequencedLegPairing`) inside inner loops. This generates significant garbage, increasing GC frequency and pausing the application.

**Evidence:**
*   **File:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
    *   **Location:** `identifyDhdFromBase` & `identifyDhdToBase` methods [L145-160, L185-200]
    *   **Analysis:** Inside a loop iterating over potential deadhead legs, a full copy of the pairing's duty info is created.
    ```java
    // LEGEND: Expensive deep copy inside a loop
    UnsequencedLegPairing tempPairing = new UnsequencedLegPairing(pairing);
    tempPairing.setFlightDutyPeriods(pairing.getFlightDutyPeriods().stream()
            .map(DutyInfo::deepCopy) // <--- Heavy allocation
            .collect(Collectors.toList()));
    ```
    *   **Impact:** If a pairing has 5 duties and there are 10 candidate DH legs, 50 `DutyInfo` objects are cloned per iteration.

*   **File:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
    *   **Location:** `updateDutyInfoList` method [L1-L15]
    *   **Analysis:** Another instance of deep copying the entire preceding label's duty list before modification.
    ```java
    List<DutyInfo> currentDutyInfoList = precedingLabel.getDutyInfoList() != null
            ? precedingLabel.getDutyInfoList().stream().map(DutyInfo::deepCopy)
            .collect(Collectors.toList())
            : new ArrayList<>();
    ```

### 2.3 Concurrency Hazards & Shared Object Mutation

**Issue:** Validation rules are designed to be stateless but inadvertently mutate the input domain objects (`UnsequencedLegPairing`, `DutyInfo`). In a concurrent environment (e.g., parallel streams or multiple threads processing the same pairing), this leads to data corruption.

**Evidence:**
*   **File:** `src/main/java/com/aa/fso/contractualrules/PilotRedeyeRule.java`
    *   **Location:** `checkRedeyeDuty` method [L1-L25]
    *   **Analysis:** The rule sets flags on the `DutyInfo` and `UnsequencedLegPairing` objects passed in.
    ```java
    // LEGEND: Mutating shared input state
    dutyPeriod.setRedeye(true); // Modifies the input object
    sequenceInfo.setRedeye(true); // Modifies the input object
    ```
    *   **Risk:** If `process()` is called concurrently on the same `pairing` instance, the `redeye` flag will be set incorrectly for other threads.

*   **File:** `src/main/java/com/aa/fso/contractualrules/BaseLayover.java`
    *   **Location:** `process` method [L1-L20]
    *   **Analysis:** Similar pattern of reading and potentially side-effecting state (though less obvious mutation here, the pattern is established).

### 2.4 Inefficient Data Structures & Algorithms

**Issue:** Simple arithmetic operations are implemented using inefficient loops, resulting in $O(N)$ complexity where $O(1)$ is available.

**Evidence:**
*   **File:** `src/main/java/com/aa/fso/util/FSOUtil.java`
    *   **Location:** `daysBetween` method [L1-L10]
    *   **Analysis:** Uses a `while` loop with `plusDays` to calculate the difference.
    ```java
    // LEGEND: O(N) implementation for date difference
    int days = 0;
    while (startDate.isBefore(endDate) && !startDate.equals(endDate)) {
      days++;
      startDate = startDate.plusDays(1); // <--- Inefficient
    }
    ```
    *   **Recommendation:** Use `ChronoUnit.DAYS.between(start, end)`.

### 2.5 Static State Contamination

**Issue:** Global static variables in utility classes are used to store transient state, which is unsafe in a multi-threaded web service.

**Evidence:**
*   **File:** `src/main/java/com/aa/fso/util/FSOUtil.java`
    *   **Location:** Class-level fields [L1-L5]
    *   **Analysis:**
    ```java
    // LEGEND: Static mutable state
    private static AccessTokenDTO accessTokenDto;
    private static String pingFederateToken;
    ```
    *   **Risk:** If `setAccessTokenDto` is called by Thread A, Thread B might read the wrong token if the timing aligns, or if the application is running multiple tenants/requests concurrently.

---

## 3. Actionable Remediations & Best Practices

### 3.1 Fix Resource Leaks (Immediate Priority)

1.  **LegDataRepositoryImpl:** Wrap `HttpURLConnection` in a `try-with-resources` block or ensure `disconnect()` is called in a `finally` block.
    ```java
    try (HttpURLConnection conn = (HttpURLConnection) FosUpdate.openConnection()) {
        // ... logic
    } finally {
        if (conn != null) conn.disconnect(); // Explicit safety
    }
    ```
2.  **AzureBlobRepositoryImpl:** Refactor to use a singleton `BlobContainerClient` or a connection pool. Do not instantiate `BlobClient` inside the hot path.
    ```java
    // Recommended: Inject a pre-configured BlobContainerClient via Spring Context
    private final BlobContainerClient containerClient;
    public void saveData(...) {
        BlobClient blobClient = containerClient.getBlobClient(fileName);
        // ... upload
    }
    ```

### 3.2 Reduce Memory Churn

1.  **Avoid Deep Copies in Loops:** Instead of cloning the entire `DutyInfo` list, create a new `UnsequencedLegPairing` and only clone the specific `DutyInfo` objects that need modification, or use a builder pattern that allows incremental updates.
2.  **Object Pooling:** If deep copying is unavoidable for logic correctness, consider using an object pool for `DutyInfo` and `Node` objects to reduce GC pressure.
3.  **Lazy Evaluation:** Defer the creation of temporary pairings until absolutely necessary (e.g., only after basic time feasibility checks pass).

### 3.3 Eliminate Concurrency Hazards

1.  **Immutable Validation:** Refactor validation rules (`PilotRedeyeRule`, `BaseLayover`, etc.) to be purely functional. They should accept inputs and return a boolean result without modifying the input objects.
    *   *Refactoring Strategy:* Remove `setRedeye(true)` calls. Instead, maintain a local `Map<String, Boolean>` or a custom result object to track state for the current validation pass.
2.  **Thread Safety:** Ensure that `UnsequencedLegPairing` objects are not shared across threads during the validation phase. If they are, create a defensive copy before passing to validators.

### 3.4 Algorithmic Optimization

1.  **Replace `daysBetween`:**
    ```java
    // Replace the loop with:
    long days = ChronoUnit.DAYS.between(startDateTime.toLocalDate(), endDateTime.toLocalDate());
    ```
2.  **Pre-compute Static Data:** Ensure `StationTimeAdjust` and `HotelCost` maps are loaded once at startup (Singleton/Cache) rather than re-loading or re-processing inside the `setFeasiblePairings` loop.

### 3.5 Flink State Management (Future Proofing)

If this codebase is migrated to Apache Flink:
1.  **Audit State Descriptors:** Search for `ValueStateDescriptor`, `MapStateDescriptor`, etc.
2.  **Enforce TTL:** Immediately call `.enableTimeToLive(Time.hours(24))` (or appropriate duration) on every state descriptor.
    ```java
    ValueStateDescriptor<Pairing, ?> descriptor = new ValueStateDescriptor<>("pairing-state", Pairing.class);
    descriptor.enableTimeToLive(Time.hours(24)); // <--- CRITICAL
    ```
3.  **Cleanup:** Ensure `CleanupConfig` is set to remove stale state automatically.

### 3.6 Static State Cleanup

1.  **Remove Static Fields:** Move `accessTokenDto` and `pingFederateToken` into a request-scoped bean or pass them as arguments.
2.  **Dependency Injection:** Use Spring's `@Scope("request")` or similar mechanisms to ensure thread-local isolation for sensitive data.