# SRE & Performance Audit Report: Sequence Builder Solver

## 1. SRE Vulnerability Summary

*   **Critical Resource Leak:** `HttpURLConnection` instances are instantiated inside `LegDataRepositoryImpl.connectToFOS` without explicit `disconnect()` calls in a `finally` block, risking socket exhaustion under load.
*   **High Memory Churn:** `DutyInfo::deepCopy` is invoked repeatedly inside tight loops within `ShortestPathComponent.identifyDhdFromBase` and `identifyDhdToBase`, creating massive garbage generation during feasibility checks.
*   **Concurrency Hazard:** `PilotRedeyeRule` mutates the shared `UnsequencedLegPairing` object (specifically `dutyPeriod.setRedeye`) during validation, which corrupts state if the same pairing object is reused or accessed concurrently.
*   **Inefficient Data Structures:** `FSOUtil.daysBetween` implements an O(N) linear scan using `plusDays` in a loop instead of utilizing `ChronoUnit.DAYS.between` for O(1) calculation.
*   **Object Creation in Loops:** `BlobClient` instances are created inside the `saveData` method of `AzureBlobRepositoryImpl` for every single write operation, bypassing connection pooling and increasing latency.
*   **Static State Mutation:** `FSOUtil` contains static setters (`setAccessTokenDto`, `setPingFederateToken`) that introduce global state, making the application non-thread-safe and difficult to scale horizontally.
*   **Missing TTL Configuration:** While not a Flink job, the codebase lacks explicit state cleanup mechanisms for large in-memory maps (e.g., `dhdHM`), potentially leading to OOM in long-running processes if data isn't pruned.

---

## 2. Detailed Vulnerability Analysis

### A. Connection & Resource Leaks

**Issue:** The `connectToFOS` method creates a new `HttpURLConnection` for every request but fails to guarantee its closure. If an exception occurs before the `try-with-resources` block completes or if the stream reading logic fails, the underlying socket remains open.

*   **File:** `src/main/java/com/aa/fso/repository/LegDataRepositoryImpl.java`
*   **Lines:** [L1-L45] (Snippet: `connectToFOS` method)
*   **Impact:** Under high concurrency or long-running batch jobs, the system will exhaust available ephemeral ports, leading to `java.net.SocketException: Too many open files` or connection timeouts.

```java
public  String connectToFOS(String script) throws IOException {
    StringBuilder response = new StringBuilder();
    try {
        URL FosUpdate = new URL("https://tapi.adt.aa.com/Service.svc");
        HttpURLConnection conn = (HttpURLConnection) FosUpdate.openConnection();
        // ... setup headers ...
        try (OutputStream os = conn.getOutputStream()) {
            // ...
        }
        // ... reading response ...
        // CRITICAL: conn.disconnect() is missing if an exception occurs before the try-with-resources closes the streams properly
        // or if the method returns early.
    } catch (Exception e) {
        e.printStackTrace();
        // No cleanup of 'conn' here
    }
    return response.toString();
}
```

**Issue:** `BlobClient` is instantiated inside the `saveData` loop. Azure SDK clients are heavy objects; creating them per write operation prevents connection reuse and increases GC pressure.

*   **File:** `src/main/java/com/aa/fso/repository/AzureBlobRepositoryImpl.java`
*   **Lines:** [L10-L25] (Snippet: `saveData` method)
*   **Impact:** Increased latency per write and unnecessary memory allocation for client builders.

```java
public boolean saveData(String folderName, String fileName, Object data, String fileExtension) {
    // ...
    try (ByteArrayInputStream dataStream = new ByteArrayInputStream(dataBytes)) {
        // BAD: Creating a new client builder and client for every single save operation
        BlobClient blobClient = currentEnvClientBuilder.blobName(folderName + "/" + fileName + fileExtension).buildClient();
        blobClient.upload(dataStream, dataBytes.length, true);
    }
    // ...
}
```

### B. High Memory Allocation Churn & GC Pressure

**Issue:** Inside `identifyDhdFromBase` and `identifyDhdToBase`, the code creates a temporary `UnsequencedLegPairing` and performs a `deepCopy` of the entire `DutyInfo` list for *every* potential deadhead leg checked. This happens inside nested loops iterating over dates and flight legs.

*   **File:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
*   **Lines:** [L145-165] (Snippet: `identifyDhdFromBase` loop)
*   **Impact:** If a pairing has 5 duties and there are 100 candidate DH legs, this creates 500+ `DutyInfo` objects and their associated `Node` lists per iteration. This generates massive garbage, causing frequent Full GCs and stalling the solver.

```java
for (int f = flightLegs.size() - 1; f >= 0; f--) {
    UnsequencedLeg flightLeg = flightLegs.get(f);
    // CRITICAL: Deep copying the entire duty list for every single candidate leg
    UnsequencedLegPairing tempPairing = new UnsequencedLegPairing(pairing);
    tempPairing.setFlightDutyPeriods(pairing.getFlightDutyPeriods().stream().map(DutyInfo::deepCopy)
            .collect(Collectors.toList()));
    
    // ... logic to check legality ...
    // If legality check fails, tempPairing is discarded, generating GC pressure
}
```

### C. Concurrency Hazards / Shared Object Mutation

**Issue:** The `PilotRedeyeRule` modifies the state of the input `UnsequencedLegPairing` object (specifically setting `dutyPeriod.setRedeye(true/false`) during the validation process. If this pairing object is stored in a cache, reused, or accessed by another thread, the state becomes corrupted.

*   **File:** `src/main/java/com/aa/fso/contractualrules/PilotRedeyeRule.java`
*   **Lines:** [L15-L35] (Snippet: `checkRedeyeDuty` method)
*   **Impact:** Non-deterministic behavior. A pairing might be marked as "Redeye" even if it shouldn't be, or a valid pairing might be rejected because a previous check mutated its state.

```java
private boolean checkRedeyeDuty(UnsequencedLegPairing sequenceInfo, Map<String, Integer> hashMap) {
    // ...
    for (int i = 0; i < dutyPeriods.size(); i++) {
        DutyInfo dutyPeriod = dutyPeriods.get(i);
        // MUTATION: Modifying the input object's internal state
        if (condition) {
            dutyPeriod.setRedeye(true); 
            sequenceInfo.setRedeye(true);
        } else {
            dutyPeriod.setRedeye(false); // This resets state for subsequent checks!
        }
    }
    return redeye;
}
```

### D. Inefficient Data Structures & Algorithms

**Issue:** The `daysBetween` utility method calculates the difference between two dates by incrementing a date variable one day at a time. This is O(N) where N is the number of days.

*   **File:** `src/main/java/com/aa/fso/util/FSOUtil.java`
*   **Lines:** [L105-L115] (Snippet: `daysBetween` method)
*   **Impact:** While likely acceptable for small N (e.g., 7 days), this pattern is an anti-pattern. If used in a hot path with large date ranges or millions of iterations, it wastes CPU cycles.

```java
public static int daysBetween(LocalDateTime startDateTime, LocalDateTime endDateTime) {
    LocalDate startDate = startDateTime.toLocalDate();
    LocalDate endDate = endDateTime.toLocalDate();
    int days = 0;
    // INEFFICIENT: Linear scan
    while (startDate.isBefore(endDate) && !startDate.equals(endDate)) {
      days++;
      startDate = startDate.plusDays(1);
    }
    days++;
    return days;
}
```

### E. Static State Contamination

**Issue:** `FSOUtil` uses static fields to store tokens and parameters (`accessTokenDto`, `pingFederateToken`). These are set via static methods.

*   **File:** `src/main/java/com/aa/fso/util/FSOUtil.java`
*   **Lines:** [L120-L130] (Snippet: `setAccessTokenDto`, `setPingFederateToken`)
*   **Impact:** In a multi-threaded environment (e.g., Spring Boot with multiple requests), Thread A might set a token for User X, and Thread B might overwrite it with User Y's token before Thread A finishes processing. This leads to authentication failures and data leakage.

```java
public static void setAccessTokenDto(final AccessTokenDTO accessTokenDto) {
    FSOUtil.accessTokenDto = accessTokenDto; // GLOBAL STATE MUTATION
}
```

---

## 3. Actionable Remediations & Best Practices

### 1. Fix Resource Leaks (Immediate Priority)
Refactor `LegDataRepositoryImpl.connectToFOS` to ensure `HttpURLConnection` is always disconnected. Use `try-with-resources` for the connection if possible, or explicitly call `disconnect()` in a `finally` block.

**Recommendation:**
```java
public String connectToFOS(String script) throws IOException {
    HttpURLConnection conn = null;
    try {
        // ... setup connection ...
        conn = (HttpURLConnection) FosUpdate.openConnection();
        // ... logic ...
        return response.toString();
    } finally {
        if (conn != null) {
            conn.disconnect(); // Ensure socket is released
        }
    }
}
```
For Azure Blob, inject a singleton `BlobContainerClient` into the repository rather than building a new client per request.

### 2. Eliminate Deep Copy Churn
Refactor `identifyDhdFromBase` and `identifyDhdToBase`. Instead of deep copying the entire `DutyInfo` list, pass the original list and a "delta" or "modification context" to the legality checker. If the check passes, *then* perform the copy. Alternatively, use immutable data structures for the temporary state.

**Recommendation:**
*   Implement a `PairingValidator` that accepts a `Pairing` and a `CandidateLeg` and returns a boolean without mutating the original.
*   Only instantiate `tempPairing` if the candidate leg is highly probable to be valid, or use a lightweight "mock" node structure for the check.

### 3. Enforce Immutability in Validation Rules
Modify `PilotRedeyeRule` and similar rules to be purely functional. They should accept the pairing, calculate the result, and return a boolean or a new validation object, without modifying the input `UnsequencedLegPairing`.

**Recommendation:**
*   Remove `dutyPeriod.setRedeye(...)` calls.
*   Store the "isRedeye" status in a local variable or a returned result object.
*   If the status needs to be persisted, do it in the caller *after* validation passes, not during the check.

### 4. Optimize Date Calculations
Replace the linear loop in `FSOUtil.daysBetween` with `ChronoUnit.DAYS.between`.

**Recommendation:**
```java
public static int daysBetween(LocalDateTime startDateTime, LocalDateTime endDateTime) {
    return (int) ChronoUnit.DAYS.between(startDateTime.toLocalDate(), endDateTime.toLocalDate()) + 1;
}
```

### 5. Remove Global Static State
Refactor `FSOUtil` to remove static setters. Pass tokens and parameters as method arguments or use dependency injection (Spring `@Configuration` beans) to manage state per request/thread.

**Recommendation:**
*   Inject `SnapshotParams` and `UserInput` into the services that need them.
*   Avoid `FSOUtil.setAccessTokenDto`. Use a `SecurityContext` or pass the token explicitly to API calls.

### 6. Flink State Management (If applicable)
If this code is part of a Flink pipeline (indicated by the prompt context), ensure that any `ValueStateDescriptor` or `MapStateDescriptor` used for caching `dhdHM` or `stationAdjustMap` has `enableTimeToLive()` configured to prevent state bloat.

**Recommendation:**
```java
// Example for Flink State
ValueStateDescriptor<UnsequencedLegPairing> stateDesc = new ValueStateDescriptor<>("pairing", UnsequencedLegPairing.class);
stateDesc.enableTimeToLive(Time.hours(24)); // Prevents unbounded growth
```
*(Note: The provided code snippets appear to be a batch solver, but if integrated into Flink, this is critical).*

### 7. Kubernetes Resource Tuning
The `k8s/IT/eastus-qa/kustomization.yaml` sets limits to 64G memory. Given the high churn identified above, ensure the JVM Heap is tuned to utilize ~75% of the limit (e.g., `-Xmx48G`) to avoid OOM kills while leaving room for off-heap buffers.

**Recommendation:**
Add JVM args to the deployment spec:
```yaml
env:
  - name: JAVA_OPTS
    value: "-Xmx48G -XX:+UseG1GC -XX:MaxGCPauseMillis=200"
```