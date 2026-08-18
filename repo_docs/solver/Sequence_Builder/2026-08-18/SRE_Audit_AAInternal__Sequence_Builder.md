# SRE & Performance Audit Report: Sequence Builder Solver

## 1. SRE Vulnerability Summary

*   **Critical Resource Leak:** `HttpURLConnection` instances are instantiated inside `LegDataRepositoryImpl.connectToFOS` without guaranteed closure in all exception paths, risking socket exhaustion.
*   **Native Memory Leak:** `OptModel` initializes FICO Xpress native resources (`XPRSprob`, `XPRB`) in `runModel` but lacks a `finally` block to explicitly close them, leading to native heap leaks on every optimization run.
*   **High GC Pressure:** Aggressive `DutyInfo::deepCopy` operations occur inside tight loops in `ShortestPathComponent.identifyDhdFromBase` and `identifyDhdToBase`, creating massive object churn during pairing generation.
*   **Concurrency Hazard:** Validation rules (e.g., `PilotRedeyeRule`) mutate shared state (`dutyPeriod.setRedeye(true)`) on input `UnsequencedLegPairing` objects, causing race conditions if the same pairing object is reused or shared across threads.
*   **Inefficient Data Structures:** `FSOUtil.daysBetween` implements an O(N) linear scan for date differences instead of using `ChronoUnit.DAYS.between`.
*   **Missing State TTL:** While no explicit Flink state descriptors were found in the provided snippets, the `ShortestPathComponent` maintains large in-memory `labelsMap` structures without TTL mechanisms, risking OOM in streaming contexts if migrated.
*   **Azure Client Instantiation:** `AzureBlobRepositoryImpl.saveData` creates a new `BlobClient` inside the method; while scoped correctly, it should be verified against a pool strategy if throughput is high.

---

## 2. Detailed Vulnerability Analysis

### 2.1 Connection & Resource Leaks (HTTP)
**Severity:** Critical
**Impact:** Socket Exhaustion, Service Degradation.

The `connectToFOS` method creates a new `HttpURLConnection` for every script execution. While `try-with-resources` is used for the streams, the `HttpURLConnection` itself is not explicitly closed in the `catch` blocks or if an exception occurs before the `try` block completes properly. If the loop in `getOpenLegs` or `getOperationLegs` runs many times, the underlying connection pool may leak sockets.

**File:** `src/main/java/com/aa/fso/repository/LegDataRepositoryImpl.java`
**Lines:** [L1-L45] (Snippet of `connectToFOS`)

```java
public  String connectToFOS(String script) throws IOException {
    StringBuilder response = new StringBuilder();
    try {
        URL FosUpdate = new URL("https://tapi.adt.aa.com/Service.svc");
        HttpURLConnection conn = (HttpURLConnection) FosUpdate.openConnection();
        // ... setup ...
        try (OutputStream os = conn.getOutputStream()) { ... }
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()))) { ... }
        // Missing: conn.disconnect() or conn.close() in a finally block
    } catch (Exception e) {
        e.printStackTrace(); // Exception swallowed, connection potentially leaked
    }
    return response.toString();
}
```

### 2.2 Native JNI C++ Memory Leaks (FICO Xpress)
**Severity:** Critical
**Impact:** Native Heap OOM, Application Crash.

The `OptModel` class interacts with the FICO Xpress Optimizer. The `runModel` method initializes the problem and runs the optimizer. However, there is no corresponding cleanup (e.g., `model.close()` or `XPRSend`) in a `finally` block. If the optimization fails, times out, or is interrupted, the native memory allocated for the problem instance remains allocated until the JVM process restarts.

**File:** `src/main/java/com/aa/fso/optmodel/OptModel.java`
**Lines:** [L1-L60] (Snippet of `runModel`)

```java
public void runModel(RunStateManager runStateManager) throws KillRunException {
    // ... initialization ...
    model.getXPRSprob().setDblControl(...);
    model.mipOptimize("d");
    
    // ... logic to parse solution ...
    
    // MISSING: Finally block to call model.close() or XPRSend
    // If an exception occurs here, native memory is leaked.
}
```

### 2.3 High Memory Allocation Churn & GC Pressure
**Severity:** High
**Impact:** High CPU usage due to GC, Latency spikes.

Inside `identifyDhdFromBase` and `identifyDhdToBase`, the code iterates through potential deadhead legs. For every candidate leg, it creates a *new* `UnsequencedLegPairing` and performs a `deepCopy` of the entire `FlightDutyPeriods` list. This happens inside nested loops (Date -> Leg -> Pairing). With thousands of legs and dates, this generates millions of short-lived objects, triggering frequent Full GCs.

**File:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
**Lines:** [L150-L175] (Snippet of `identifyDhdFromBase`)

```java
for (int f = flightLegs.size() - 1; f >= 0; f--) {
    UnsequencedLeg flightLeg = flightLegs.get(f);

    // CRITICAL: Creates a new Pairing and Deep Copies the entire Duty List
    UnsequencedLegPairing tempPairing = new UnsequencedLegPairing(pairing);
    tempPairing.setFlightDutyPeriods(pairing.getFlightDutyPeriods().stream()
            .map(DutyInfo::deepCopy) // Expensive operation inside loop
            .collect(Collectors.toList()));
            
    // ... logic ...
}
```

### 2.4 Concurrency Hazards / Shared Object Mutation
**Severity:** High
**Impact:** Data Corruption, Incorrect Legality Checks.

Validation rules like `PilotRedeyeRule` and `FARedeyeRule` modify the state of the input `UnsequencedLegPairing` object (specifically setting `dutyPeriod.setRedeye(true)`). If these pairings are cached, reused, or processed concurrently (e.g., in a parallel stream), the mutation will corrupt the state for other threads or subsequent checks.

**File:** `src/main/java/com/aa/fso/contractualrules/PilotRedeyeRule.java`
**Lines:** [L15-L35] (Snippet of `checkRedeyeDuty`)

```java
private boolean checkRedeyeDuty(UnsequencedLegPairing sequenceInfo, Map<String, Integer> hashMap) {
    // ...
    for (int i = 0; i < dutyPeriods.size(); i++) {
        DutyInfo dutyPeriod = dutyPeriods.get(i);
        // MUTATION: Modifying the input object's state
        if (/* condition */) {
            dutyPeriod.setRedeye(true); // Side effect!
            sequenceInfo.setRedeye(true);
        } else {
            dutyPeriod.setRedeye(false); // Side effect!
        }
    }
    return redeye;
}
```

### 2.5 Inefficient Data Structures (O(N) Scans)
**Severity:** Medium
**Impact:** Increased CPU time for simple calculations.

The `daysBetween` utility method calculates the difference between two dates using a `while` loop incrementing by one day. This is O(N) where N is the number of days. For a 7-day window, it's negligible, but for larger ranges or high-frequency calls, it is inefficient compared to standard library methods.

**File:** `src/main/java/com/aa/fso/util/FSOUtil.java`
**Lines:** [L1-L15] (Snippet of `daysBetween`)

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

### 2.6 Flink State TTL Leaks (Potential)
**Severity:** Low (Context Dependent)
**Impact:** Memory Leaks in Streaming.

While the provided code appears to be batch-oriented (or a custom graph solver), if this logic were ported to Flink, the `labelsMap` in `createLabelsMap` accumulates state without any TTL mechanism. In a streaming context, this would grow indefinitely.

**File:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
**Lines:** [L100-L120] (Snippet of `createLabelsMap`)

```java
Map<Integer, Map<Integer, Label>> labelsMap = new HashMap<Integer, Map<Integer, Label>>();
// ... population logic ...
// No enableTimeToLive() or state descriptor configuration visible.
```

---

## 3. Actionable Remediations & Best Practices

### 3.1 Fix Resource Leaks (HTTP & Native)
*   **Action:** Refactor `LegDataRepositoryImpl.connectToFOS` to ensure `conn.disconnect()` is called in a `finally` block. Better yet, use `HttpClient` (Java 11+) which manages connection pooling automatically.
*   **Action:** Refactor `OptModel.runModel` to wrap the optimization logic in a `try-finally` block. Call `model.close()` or the specific FICO Xpress cleanup methods in the `finally` block to guarantee native memory release.

```java
// Example for OptModel
public void runModel(...) {
    try {
        // ... optimization logic ...
    } finally {
        if (model != null) {
            model.close(); // Ensure native cleanup
        }
    }
}
```

### 3.2 Reduce GC Pressure
*   **Action:** Avoid `deepCopy` inside inner loops. Instead of copying the whole `DutyInfo` list, create a lightweight "TestContext" or "Candidate" object that holds references to the original data plus the specific changes (the new DH leg). Only perform the deep copy if the candidate passes all legality checks.
*   **Action:** Reuse `UnsequencedLegPairing` instances by resetting their state rather than creating new ones, if the logic allows.

### 3.3 Eliminate Concurrency Hazards
*   **Action:** Refactor validation rules (`PilotRedeyeRule`, etc.) to be **stateless**. They should accept the pairing, calculate the result, and return a boolean, without modifying the input object.
*   **Action:** If state modification is absolutely required for downstream logic, make a defensive copy of the pairing *before* passing it to the validator, or ensure the validator returns a new modified object.

```java
// Recommended Pattern
public boolean isRedeyeLegal(UnsequencedLegPairing pairing) {
    // Read-only logic
    for (DutyInfo duty : pairing.getFlightDutyPeriods()) {
        if (/* check */) return false;
    }
    return true;
}
```

### 3.4 Optimize Algorithms
*   **Action:** Replace `FSOUtil.daysBetween` with `ChronoUnit.DAYS.between(start, end)`. This reduces complexity from O(N) to O(1).

```java
// Replacement
public static int daysBetween(LocalDateTime start, LocalDateTime end) {
    return (int) ChronoUnit.DAYS.between(start.toLocalDate(), end.toLocalDate());
}
```

### 3.5 Future-Proofing for Flink
*   **Action:** If migrating to Flink, ensure all `ValueStateDescriptor`, `MapStateDescriptor`, etc., are initialized with `enableTimeToLive(Time.hours(24))` or similar to prevent state bloat.
*   **Action:** Implement proper checkpointing strategies for the `labelsMap` if it becomes part of the state backend.

### 3.6 Azure Client Strategy
*   **Action:** Review `AzureBlobRepositoryImpl`. While `blobClient` is closed via try-with-resources, ensure the `BlobClientBuilder` or `BlobServiceClient` is instantiated once per application lifecycle (Singleton) rather than per request if possible, to reduce connection overhead.