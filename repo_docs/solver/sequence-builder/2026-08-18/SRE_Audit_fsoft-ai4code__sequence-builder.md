# SRE & Performance Audit Report: Flight Schedule Optimization (FSO) Solver

## 1. SRE Vulnerability Summary

*   **Critical Memory Leak (High Churn):** `ShortestPathComponent` performs deep cloning of `DutyInfo` objects inside tight loops (`identifyDhdFromBase`, `identifyDhdToBase`) for every potential deadhead leg, causing massive garbage generation and GC pressure.
*   **Resource Leak (I/O):** `JsonUtil.saveToJsonFile` creates a new `ObjectMapper` instance for every single file write operation, bypassing efficient serialization caching and increasing CPU overhead.
*   **Concurrency Hazard:** `RunStateManager` is documented as a singleton but lacks explicit synchronization or thread-safe implementation details in the provided snippet, risking race conditions in multi-threaded solver environments.
*   **Inefficient Data Structures:** `ShortestPathComponent` uses `LinkedList` for `FlightNodes` and performs repeated `add(0, ...)` operations (O(N)) inside path reconstruction loops.
*   **Resource Leak (Network):** `LegDataRepositoryImpl.connectToFOS` creates `HttpURLConnection` instances inside a loop without ensuring proper `disconnect()` calls in all exception paths, potentially exhausting socket pools.
*   **Algorithmic Complexity:** `ConstructNetwork.buildNetwork` implements an $O(N^2)$ edge construction algorithm with nested loops over all nodes, which will scale poorly as flight volume increases.
*   **Missing State TTL:** While not a Flink job, the codebase relies heavily on in-memory `Map` structures (`labelsMap`, `dhdHM`) that grow indefinitely without eviction policies, risking OutOfMemory errors during large-scale runs.

---

## 2. Detailed Vulnerability Analysis

### A. High Memory Allocation Churn & GC Pressure

**Issue:** The code aggressively clones complex objects (`DutyInfo`, `UnsequencedLegPairing`) inside inner loops used for feasibility checking. This creates thousands of short-lived objects per second, triggering frequent Full GC cycles.

**Location:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
**Lines:** `identifyDhdFromBase` [L145-150] & `identifyDhdToBase` [L185-190]

```java
// Inside identifyDhdFromBase loop
for (int f = flightLegs.size() - 1; f >= 0; f--) {
    UnsequencedLeg flightLeg = flightLegs.get(f);

    // CRITICAL: Deep copying the entire duty list for every single candidate leg
    UnsequencedLegPairing tempPairing = new UnsequencedLegPairing(pairing);
    tempPairing.setFlightDutyPeriods(pairing.getFlightDutyPeriods().stream()
            .map(DutyInfo::deepCopy) // Expensive operation inside a loop
            .collect(Collectors.toList()));
    
    // ... further processing ...
}
```

**Impact:** If a base has 1000 candidate deadhead legs and 5 duties per pairing, this results in 5,000 object allocations per iteration. In a production environment with hundreds of bases, this leads to severe latency spikes.

### B. Inefficient Data Structures & Algorithms

**Issue 1:** Using `LinkedList` with `add(0, ...)` for building flight node lists.
**Issue 2:** $O(N^2)$ complexity in network construction.

**Location:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
**Lines:** `setFeasiblePairings` [L45-50]

```java
while (precedingNodeIndex != 0 && precedingNodeIndex != -1) {
    // ...
    if (precedingLabel.getNode().getIndex() != 0) {
        // O(N) operation inside a loop: LinkedList.add(0, element) shifts all elements
        pairing.getFlightNodes().add(0, precedingLabel.getNode()); 
    }
    // ...
}
```

**Location:** `src/main/java/com/aa/fso/processor/ConstructNetwork.java`
**Lines:** `buildNetwork` [L130-135]

```java
// O(N^2) Nested Loop for Edge Construction
for (int i = 0; i < nodes.size() - 1; i++) {
    for (int j = 1; j < nodes.size(); j++) {
        // Logic to determine connectivity...
    }
}
```

**Impact:**
1.  **Reconstruction:** As path length grows, the cost of prepending to a linked list increases linearly, making path reconstruction $O(L^2)$ where $L$ is path length.
2.  **Network Build:** With $N$ flights, the edge construction becomes quadratic. If $N=10,000$, this performs 100 million iterations just to build the graph, likely causing timeouts before optimization even starts.

### C. Resource Leaks (I/O & Network)

**Issue 1:** Creating `ObjectMapper` instances repeatedly.
**Issue 2:** Potential socket leaks in HTTP connections.

**Location:** `src/main/java/com/aa/fso/util/JsonUtil.java`
**Lines:** `saveToJsonFile` [L10-12]

```java
public static void saveToJsonFile(Object object, String fileName) {
    ObjectMapper obj = new ObjectMapper(); // NEW INSTANCE EVERY CALL
    // ...
}
```

**Location:** `src/main/java/com/aa/fso/repository/LegDataRepositoryImpl.java`
**Lines:** `connectToFOS` [L20-45]

```java
public String connectToFOS(String script) throws IOException {
    // ...
    HttpURLConnection conn = (HttpURLConnection) FosUpdate.openConnection();
    // ...
    // Missing explicit conn.disconnect() in all catch blocks or finally blocks
    // If an exception occurs before the try-with-resources block (if any), socket stays open
}
```

**Impact:**
1.  **JSON:** Serialization overhead increases significantly due to repeated initialization of the mapper.
2.  **HTTP:** In high-throughput scenarios (e.g., fetching open legs for many dates), failing to disconnect can exhaust the system's ephemeral port pool or connection limits.

### D. Concurrency Hazards & Singleton State

**Issue:** `RunStateManager` is described as a singleton managing a kill flag. Without explicit synchronization or `volatile` keyword usage on the kill flag, concurrent threads might not see updates immediately, leading to delayed termination or race conditions.

**Location:** `src/main/java/com/aa/fso/service/RunStateManager.java`
**Context:** Class definition implies singleton behavior.

```java
public class RunStateManager {
    // Likely missing: private volatile boolean killRequested = false;
    // Likely missing: synchronized methods or atomic references
}
```

**Impact:** In a distributed or multi-threaded solver, the "kill" signal might not propagate correctly, causing the application to hang or fail to terminate gracefully during scaling events.

### E. Flink State TTL (Contextual Note)

**Observation:** The provided codebase appears to be a batch/stream hybrid Java application (likely running on Kubernetes/Cloud), not a native Flink job. However, the `labelsMap` and `dhdHM` structures act as in-memory state stores.

**Risk:** These maps (`Map<Integer, Map<Integer, Label>>`) are populated in `createLabelsMap` and held in memory until the method returns. There is no TTL or eviction mechanism. If the input data scales, these maps will grow until they cause an `OutOfMemoryError`.

**Location:** `src/main/java/com/aa/fso/processor/ShortestPathComponent.java`
**Lines:** `createLabelsMap` [L1-10]

```java
Map<Integer, Map<Integer, Label>> labelsMap = new HashMap<>();
// ... population logic ...
return labelsMap; // Entire map returned, held in memory
```

---

## 3. Actionable Remediations & Best Practices

### Immediate Fixes (High Priority)

1.  **Refactor Deep Cloning Strategy:**
    *   **Action:** Avoid `deepCopy` inside the inner loop. Instead, use a "undo" stack or a lightweight builder pattern to modify the temporary pairing, revert changes after the check, and reuse the object.
    *   **Alternative:** If immutability is required, consider using immutable data structures (e.g., Google Guava `ImmutableList`) or a specialized object pool for `DutyInfo` lists.
    *   **Code Change:** Move `tempPairing` creation outside the loop if possible, or implement a `cloneAndRollback` mechanism.

2.  **Optimize Data Structures:**
    *   **Action:** Replace `LinkedList` with `ArrayList` and `Collections.reverse()` for path reconstruction.
    *   **Action:** Replace the $O(N^2)$ edge construction with a spatial index (e.g., `TreeMap` or `IntervalTree`) keyed by time/station to reduce edge lookups to $O(N \log N)$ or $O(N)$.

3.  **Fix Resource Management:**
    *   **Action:** Make `ObjectMapper` a static singleton or use dependency injection (Spring Bean) to reuse the instance.
    *   **Action:** Wrap `HttpURLConnection` in a `try-with-resources` block or ensure `conn.disconnect()` is called in a `finally` block.

    ```java
    // Example Fix for JSON Util
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    public static void saveToJsonFile(Object object, String fileName) {
        try (FileWriter fileWriter = new FileWriter(fileName)) {
            OBJECT_MAPPER.writeValue(fileWriter, object);
        } catch (IOException e) {
            // handle
        }
    }
    ```

4.  **Strengthen Concurrency:**
    *   **Action:** Ensure `RunStateManager` uses `AtomicBoolean` for the kill flag and `volatile` for visibility across threads.

### Long-Term Architectural Improvements

1.  **Implement State TTL/Eviction:**
    *   If this logic is moved to Flink or a long-running service, replace `HashMap` with `ConcurrentHashMap` combined with a TTL policy (e.g., using Caffeine cache with expiration) for `labelsMap` entries to prevent memory bloat.

2.  **Parallel Processing:**
    *   The `generateSolutionSpace` method iterates over bases sequentially. Refactor this to use a `ForkJoinPool` or `CompletableFuture` to process multiple bases in parallel, utilizing available CPU cores effectively.

3.  **Streaming/Chunking:**
    *   For `createLabelsMap`, process nodes in batches rather than loading the entire graph into memory at once. Stream the topological sort results to keep memory footprint constant relative to the batch size.

4.  **Monitoring & Observability:**
    *   Add metrics for:
        *   Number of `DutyInfo` clones per second.
        *   Heap usage growth during `buildNetwork`.
        *   HTTP connection pool utilization.
    *   Implement circuit breakers for external FOS API calls to prevent cascading failures.