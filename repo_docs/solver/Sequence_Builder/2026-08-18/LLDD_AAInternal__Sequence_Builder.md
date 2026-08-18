# Low-Level Design Document (LLDD)

## Module: src

### Relationships & Calls

```mermaid
flowchart TD
    sym_0["CLASS: SequenceBuilderApplication"]
    sym_1["CLASS: Constants"]
    sym_2["CLASS: DateTimeDTO"]
    sym_3["CLASS: SequenceKeyDTO"]
    sym_4["CLASS: SolverResponseDTO"]
    sym_5["CLASS: SolverResponseSummaryDTO"]
    sym_6["CLASS: StudentScheduleDTO"]
    sym_7["CLASS: FlightLegDTO"]
    sym_8["CLASS: EmployeeActivityDTO"]
    sym_9["CLASS: AccessTokenDTO"]
    sym_10["CLASS: PlaceHolderEvents"]
    sym_11["CLASS: CKAScheduleDTO"]
    sym_12["CLASS: SnapshotSolutionRequestInputDTO"]
    sym_13["CLASS: LocalDateDeserializer"]
    sym_14["CLASS: MyErrorResponse"]
    sym_15["CLASS: OEActivityDTO"]
    sym_16["CLASS: FetchJobOutputDTO"]
    sym_17["CLASS: FlightDutyPeriodDTO"]
    sym_18["CLASS: LocalDateSerializer"]
    sym_19["CLASS: SequenceDTO"]
    sym_20["CLASS: FARedeyeRule"]
    sym_21["CLASS: PilotDomesticSequenceRule"]
    sym_22["CLASS: WOCL"]
    sym_23["CLASS: ThreeAMHBT"]
    sym_24["CLASS: BaseLayover"]
    sym_25["CLASS: PilotRedeyeRule"]
    sym_26["CLASS: AzureBlobRepositoryImpl"]
    sym_27["CLASS: AzureBlobRepository"]
    sym_28["CLASS: PingFederateTokenClient"]
    sym_29["CLASS: AccessTokenClient"]
    sym_30["CLASS: QLAClientImpl"]
    sym_31["CLASS: OutputDataRepositoryImpl"]
    sym_32["CLASS: PingFederateTokenClientImpl"]
    sym_33["CLASS: AccessTokenClientImpl"]
    sym_34["CLASS: LegDataRepository"]
    sym_35["CLASS: QLAClient"]
    sym_36["CLASS: InputDataRepositoryImpl"]
    sym_37["CLASS: LegDataRepositoryImpl"]
    sym_38["CLASS: InputDataRespository"]
    sym_39["CLASS: OutputDataRepository"]
    sym_40["CLASS: KafkaProducerListener"]
    sym_41["CLASS: JsonUtil"]
    sym_42["CLASS: SurfaceLegLoader"]
    sym_43["CLASS: TAPIUtil"]
    sym_44["CLASS: SnapshotValidator"]
    sym_45["CLASS: StringUtil"]
    sym_46["CLASS: FSOFileWriter"]
    sym_47["CLASS: StationTimeAdjustLoader"]
    sym_48["CLASS: FSOUtil"]
    sym_49["CLASS: CompressUtil"]
    sym_50["CLASS: SecurityConfig"]
    sym_51["CLASS: AzureBlobStorageConfiguration"]
    sym_52["CLASS: KafkaCallbackConfig"]
    sym_53["CLASS: KafkaConfig"]
    sym_54["CLASS: KafkaConsumerConfig"]
    sym_55["CLASS: KafkaProducerConfig"]
    sym_56["CLASS: ServicePrincipalAuthCallbackSB"]
    sym_57["CLASS: ShortestPathComponent"]
    sym_58["CLASS: QLAProcessor"]
    sym_59["CLASS: CKAProcessor"]
    sym_60["CLASS: StaticDataProcessor"]
    sym_61["CLASS: InputValidationProcessor"]
    sym_62["CLASS: DHProcessor"]
    sym_63["CLASS: ConstructNetwork"]
    sym_64["CLASS: SequenceProcessor"]
    sym_65["CLASS: CkaMapper"]
    sym_66["CLASS: StudentMapper"]
    sym_67["CLASS: SequenceMapper"]
    sym_68["CLASS: QLAMapper"]
    sym_69["CLASS: TeamsNotification"]
    sym_70["CLASS: HttpSolverController"]
    sym_71["CLASS: KillController"]
    sym_72["CLASS: AzureBlobController"]
    sym_73["CLASS: FlightController"]
    sym_74["CLASS: AppProperties"]
    sym_75["CLASS: TeamsNotifications"]
    sym_76["CLASS: LegalityInterpreterRepositoryImpl"]
    sym_77["CLASS: QlaResponse"]
    sym_78["CLASS: EmployeeQLAResponse"]
    sym_79["CLASS: LegalityInterpreter"]
    sym_80["CLASS: InvalidSeqMapper"]
    sym_81["CLASS: LegalityInterpreterRepository"]
    sym_82["CLASS: PilotLegalityResponse"]
    sym_83["CLASS: PersistenceException"]
    sym_84["CLASS: LegalityRuleResult"]
    sym_85["FUNCTION: value"]
    sym_86["FUNCTION: Result"]
    sym_87["FUNCTION: toString"]
    sym_88["CLASS: RuleResult"]
    sym_89["FUNCTION: value"]
    sym_90["FUNCTION: Rule"]
    sym_91["FUNCTION: toString"]
    sym_92["CLASS: EmployeeResponse"]
    sym_93["CLASS: PickupDuty"]
    sym_94["CLASS: DateTimeInfo"]
    sym_95["CLASS: FlightLeg"]
    sym_96["CLASS: FlightDutyPeriod"]
    sym_97["CLASS: CrewMemberKey"]
    sym_98["CLASS: SequenceDetail"]
    sym_99["CLASS: CrewMemberInfo"]
    sym_100["CLASS: ProjectedData"]
    sym_101["CLASS: ScheduledTime"]
    sym_102["CLASS: DutyPeriods"]
    sym_103["CLASS: FlightDutyPeriodKey"]
    sym_104["CLASS: SequenceInfoKey"]
    sym_105["CLASS: LocalDateTimeDeserializer"]
    sym_106["CLASS: LocalDateTimeSerializer"]
    sym_107["CLASS: BidStatus"]
    sym_108["CLASS: EmpCaatsData"]
    sym_109["CLASS: LocalDateDeserializer"]
    sym_110["CLASS: FlightKey"]
    sym_111["CLASS: SequenceInfo"]
    sym_112["CLASS: EmployeeRequest"]
    sym_113["CLASS: ValidationConstants"]
    sym_114["CLASS: PilotLegalityRequest"]
    sym_115["CLASS: TimeInfo"]
    sym_116["CLASS: LocalDateSerializer"]
    sym_117["CLASS: Employee"]
    sym_118["CLASS: FlightLegs"]
    sym_119["CLASS: StationLongitudeUtils"]
    sym_120["CLASS: QLACallableClient"]
    sym_121["CLASS: QLARestClient"]
    sym_122["CLASS: FlightLeg"]
    sym_123["CLASS: Solution"]
    sym_124["CLASS: UnsequencedLegAfterRun"]
    sym_125["CLASS: SurfaceLeg"]
    sym_126["CLASS: DutyInfo"]
    sym_127["CLASS: Sequence"]
    sym_128["CLASS: Node"]
    sym_129["CLASS: Label"]
    sym_130["CLASS: HotelCostLoader"]
    sym_131["CLASS: FlightInfo"]
    sym_132["CLASS: ProcessedInputData"]
    sym_133["CLASS: FlightDutyPeriod"]
    sym_134["CLASS: Destinations"]
    sym_135["CLASS: Base"]
    sym_136["CLASS: HotelCost"]
    sym_137["CLASS: Network"]
    sym_138["CLASS: CkaBlankPeriod"]
    sym_139["CLASS: UnsequencedLegPairing"]
    sym_140["CLASS: UnsequencedLeg"]
    sym_141["CLASS: Cka"]
    sym_142["CLASS: PositionBasedParams"]
    sym_143["CLASS: BaseResourcesDeserializer"]
    sym_144["CLASS: BaseCoterminalsMap"]
    sym_145["CLASS: PairingSolution"]
    sym_146["CLASS: FilteredFlightData"]
    sym_147["CLASS: LocalDateTimeDeserializer"]
    sym_148["CLASS: LocalDateTimeSerializer"]
    sym_149["CLASS: ITFlightKey"]
    sym_150["CLASS: CkaCredits"]
    sym_151["CLASS: FlightKey"]
    sym_152["CLASS: VacationCredit"]
    sym_153["CLASS: Coterminals"]
    sym_154["CLASS: StationTimeAdjust"]
    sym_155["CLASS: ParentSnapshotParams"]
    sym_156["CLASS: ValidationConstants"]
    sym_157["CLASS: Student"]
    sym_158["CLASS: SequencedPosition"]
    sym_159["CLASS: EmployeeActivity"]
    sym_160["CLASS: OutputData"]
    sym_161["CLASS: BaseExclusionKey"]
    sym_162["CLASS: Edge"]
    sym_163["CLASS: AvailableDHLeg"]
    sym_164["CLASS: SnapshotParams"]
    sym_165["CLASS: DHDCategorization"]
    sym_166["CLASS: UserInput"]
    sym_167["CLASS: FAR117FTRule"]
    sym_168["CLASS: FAR121FDPRule"]
    sym_169["CLASS: FAR117RestTimeRule"]
    sym_170["CLASS: FAR121RestTimeRule"]
    sym_171["CLASS: FAR117FDPRule"]
    sym_172["CLASS: FAR121FTRule"]
    sym_173["CLASS: ModelParams"]
    sym_174["CLASS: is"]
    sym_175["CLASS: OptModel"]
    sym_176["CLASS: ErrorConstants"]
    sym_177["CLASS: ITDataServiceImpl"]
    sym_178["CLASS: SolverService"]
    sym_179["CLASS: PairingGenerationService"]
    sym_180["CLASS: OptimizationService"]
    sym_181["CLASS: PairingGenerationServiceImpl"]
    sym_182["CLASS: to"]
    sym_183["CLASS: OptimizationServiceImpl"]
    sym_184["CLASS: ITDataService"]
    sym_185["CLASS: PairingHeaderServiceImpl"]
    sym_186["CLASS: RunStateManager"]
    sym_187["CLASS: OutputDataService"]
    sym_188["CLASS: InputDataService"]
    sym_189["CLASS: PairingHeaderService"]
    sym_190["CLASS: OutputDataServiceImpl"]
    sym_191["CLASS: InputDataServiceImpl"]
    sym_192["CLASS: SequenceBuilderSpringContext"]
    sym_193["CLASS: OAuthBearerTokenImpl"]
    sym_194["CLASS: KafkaProducerService"]
    sym_195["CLASS: KafkaConsumerService"]
    sym_196["CLASS: SolverException"]
    sym_197["CLASS: SolverExceptionHandler"]
    sym_198["CLASS: AzureBlobStorageException"]
    sym_199["CLASS: InvalidUserInputException"]
    sym_200["CLASS: KillRunException"]
    sym_201["CLASS: NotFoundException"]
```

# Low-Level Design Document (LLDD): Sequence Builder Module

## 1. Overview
This document details the internal architecture, class structures, and behavioral logic of the `Sequence Builder` module. The system is designed to automate the generation of pilot pairing sequences while adhering to complex contractual rules (FAR 117, FAR 121), legal constraints, and operational requirements. It integrates with external systems via REST APIs, Azure Blob Storage, and Kafka for asynchronous processing.

The design emphasizes separation of concerns:
*   **DTOs**: Data transfer objects for API boundaries.
*   **Models**: Internal domain entities representing the optimization graph.
*   **Services**: Business logic orchestration.
*   **Repositories**: Abstraction over data persistence (Azure Blob, External APIs).
*   **Rules**: Encapsulated logic for legality checks.

---

## 2. Core Domain Objects & DTOs

### 2.1 Data Transfer Objects (DTOs)
These classes serve as the contract between the API layer and internal processing logic. They are typically immutable or use standard JavaBean patterns with Jackson annotations for serialization.

#### `SequenceBuilderApplication`
*   **Location:** [`src/main/java/com/aa/fso/SequenceBuilderApplication.java:L12-12`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/SequenceBuilderApplication.java#L12-12)
*   **Behavior:** The Spring Boot entry point. Initializes the application context and enables auto-configuration for Kafka, Security, and Azure services.
*   **Implementation Note:** Uses `@SpringBootApplication` to bootstrap the microservice.

#### `Constants`
*   **Location:** [`src/main/java/com/aa/fso/Constants.java:L3-3`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/Constants.java#L3-3)
*   **Behavior:** Holds static final values for file extensions, default time formats, and magic numbers used across the module.
*   **Usage:** Prevents "magic string" errors by centralizing configuration values.

#### `DateTimeDTO`, `SequenceKeyDTO`, `SolverResponseDTO`, etc.
*   **Locations:** Various under `dto/` package.
*   **Behavior:** These classes act as thin wrappers for JSON payloads.
    *   `DateTimeDTO`: Wraps date/time logic to ensure consistent ISO-8601 formatting during deserialization.
    *   `SolverResponseDTO`: Aggregates the final output of the optimization engine, including success status, solution ID, and error messages.
    *   `SnapshotSolutionRequestInputDTO`: Captures the user's input parameters required to trigger a new solving session.
*   **Error Handling:** Deserialization failures (e.g., invalid date format) are caught by global exception handlers, converting them into `400 Bad Request` responses.

#### `FlightLegDTO`, `EmployeeActivityDTO`, `StudentScheduleDTO`
*   **Locations:** `dto/` package.
*   **Behavior:** Represent specific segments of the scheduling problem.
    *   `FlightLegDTO`: Contains origin, destination, departure/arrival times, and aircraft type.
    *   `EmployeeActivityDTO`: Tracks an employee's historical or projected activities (rest, duty, vacation).
*   **Design Pattern:** Follows the **Data Mapper** pattern where these DTOs are transformed into internal `Model` objects before processing.

#### `LocalDateSerializer` / `LocalDateDeserializer`
*   **Locations:** `dto/` and `qlacheck/request/` packages.
*   **Behavior:** Custom Jackson serializers/deserializers to handle `java.time.LocalDate` and `LocalDateTime`.
*   **Implementation Detail:** Ensures that dates are parsed strictly according to the configured pattern (e.g., `yyyy-MM-dd`) to avoid timezone ambiguity issues common in legacy systems.

---

## 3. Domain Models & Graph Structures

The core optimization logic relies on a graph-based representation of the scheduling problem.

#### `Network`, `Node`, `Edge`
*   **Locations:** `model/` package.
*   **Behavior:**
    *   `Network`: Represents the entire graph of possible pairings.
    *   `Node`: Represents a specific state in the schedule (e.g., "Pilot at Base A after Flight 123").
    *   `Edge`: Represents a transition between nodes (e.g., "Fly Flight 456 from Base A to Base B").
*   **Algorithmic Role:** The `OptModel` class uses these to construct a shortest-path problem (often solved using Label Correcting algorithms).

#### `Sequence`, `Solution`, `PairingSolution`
*   **Locations:** `model/` package.
*   **Behavior:**
    *   `Sequence`: A valid chain of flight legs assigned to a single crew member.
    *   `Solution`: The aggregate result containing multiple `Sequence` objects that cover all required flights.
    *   `PairingSolution`: A specific view of a sequence optimized for cost or fairness.
*   **State Management:** These objects are mutable during the construction phase but become immutable once validated and returned.

#### `UnsequencedLeg`, `UnsequencedLegPairing`
*   **Locations:** `model/` package.
*   **Behavior:** Represents raw flight data that has not yet been assigned to a sequence. The `ConstructNetwork` processor iterates over these to build the `Network` graph.

#### `Cka`, `CkaCredits`, `CkaBlankPeriod`
*   **Locations:** `model/` package.
*   **Behavior:** Specific models for "Crew Key Assignment" (CKA) logic, handling credits earned, blank periods (gaps in work), and specific contractual entitlements.

---

## 4. Business Logic & Rules Engine

The module enforces strict regulatory compliance through a rule-based architecture.

#### Contractual Rules (`contractualrules/`)
*   **Classes:** `FARRedeyeRule`, `PilotDomesticSequenceRule`, `WOCL`, `ThreeAMHBT`, `BaseLayover`, `PilotRedeyeRule`.
*   **Behavior:**
    *   Each class implements a specific regulation check.
    *   **Example (`WOCL`):** Checks for "Weekend Off Cycle Limit" violations.
    *   **Example (`ThreeAMHBT`):** Validates minimum rest periods if a duty starts before 03:00 AM.
*   **Execution:** These rules are invoked by the `LegalityInterpreter` during the validation phase. If a rule returns `false`, the sequence is marked illegal.

#### Regulatory Rules (`rules/`)
*   **Classes:** `FAR117FTRule`, `FAR121FDPRule`, `FAR117RestTimeRule`, `FAR121RestTimeRule`.
*   **Behavior:**
    *   **`FAR117FTRule`**: Validates flight time limits based on duty start time and crew size.
        *   *Logic:* Calculates total flight time in a duty period and compares it against the maximum allowed hours defined in FAR 117.
    *   **`FAR121FDPRule`**: Enforces Flight Duty Period (FDP) limits specific to Part 121 operations.
*   **Error Handling:** Violations throw `SolverException` or return structured `RuleResult` objects indicating the specific violation code.

#### `LegalityInterpreter` & `LegalityInterpreterRepository`
*   **Locations:** `qlacheck/response/` package.
*   **Behavior:**
    *   Acts as the central orchestrator for legality checks.
    *   Accepts a `PilotLegalityRequest` and iterates through all applicable rules.
    *   Returns a `PilotLegalityResponse` containing a list of `RuleResult` objects.
*   **Interface:** `LegalityInterpreterRepository` defines the contract for fetching rule configurations or historical data.

---

## 5. Services & Orchestration

### 5.1 Core Services
*   **`SolverService`**: [`src/main/java/com/aa/fso/service/SolverService.java:L31-31`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/service/SolverService.java#L31-31)
    *   **Behavior:** The primary entry point for solving requests. Coordinates input validation, network construction, optimization execution, and output formatting.
    *   **Flow:** `InputValidation` -> `ConstructNetwork` -> `Optimization` -> `LegalityCheck` -> `Output`.

*   **`OptimizationService` / `OptimizationServiceImpl`**:
    *   **Behavior:** Interfaces with the underlying mathematical solver (likely Xpress or similar).
    *   **Implementation:** Wraps the solver API calls, handling timeouts and memory constraints.

*   **`PairingGenerationService` / `PairingGenerationServiceImpl`**:
    *   **Behavior:** Handles the post-processing of the raw optimization output to generate human-readable pairings.
    *   **Logic:** Aggregates `Sequence` objects, applies cost functions, and ensures coverage of all unsequenced legs.

*   **`RunStateManager`**: [`src/main/java/com/aa/fso/service/RunStateManager.java:L20-20`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/service/RunStateManager.java#L20-20)
    *   **Behavior:** Manages the lifecycle of a solver run.
    *   **Key Feature:** Implements a **volatile kill flag**. When a `KillController` request is received, this flag is set. The `OptimizationService` checks this flag at periodic checkpoints to gracefully terminate the solver process.
    *   **Singleton:** Ensures only one run executes per pod instance to prevent resource contention.

### 5.2 Data Services
*   **`InputDataService` / `OutputDataService`**: Handle the ingestion of raw CSV/JSON inputs and the persistence of results to Azure Blob Storage.
*   **`ITDataService`**: Interfaces with external IT systems to fetch static data (e.g., airport codes, base locations).

---

## 6. Infrastructure & Integration

### 6.1 Repositories & Clients
*   **`AzureBlobRepository` / `AzureBlobRepositoryImpl`**:
    *   **Behavior:** Abstracts interactions with Azure Blob Storage.
    *   **Methods:** `uploadFile`, `downloadFile`, `deleteFile`.
    *   **Error Handling:** Wraps Azure SDK exceptions into `AzureBlobStorageException`.

*   **`QLAClient` / `QLAClientImpl`**:
    *   **Behavior:** REST client for communicating with the QLA (Quality Assurance/Logistics Application) external service.
    *   **Retry Logic:** Implements exponential backoff for transient network failures.

*   **`PingFederateTokenClient` / `AccessTokenClient`**:
    *   **Behavior:** Handles OAuth2 authentication flows.
    *   **Flow:** Exchanges client credentials for an access token, caches it, and refreshes it upon expiration.

### 6.2 Messaging (Kafka)
*   **`KafkaProducerService` / `KafkaConsumerService`**:
    *   **Behavior:** Asynchronous communication layer.
    *   **Producer:** Publishes job completion events or error notifications.
    *   **Consumer:** Listens for external job triggers (e.g., "Start Solving Job ID 123").
*   **`KafkaProducerListener`**: [`src/main/java/com/aa/fso/listener/KafkaProducerListener.java:L12-12`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/listener/KafkaProducerListener.java#L12-12)
    *   **Behavior:** Intercepts successful message sends to trigger side effects (e.g., sending a Teams notification).

### 6.3 Controllers
*   **`HttpSolverController`**: [`src/main/java/com/aa/fso/controller/HttpSolverController.java:L31-31`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/controller/HttpSolverController.java#L31-31)
    *   **Behavior:** Exposes REST endpoints (`POST /solve`, `GET /status`).
    *   **Async Handling:** Returns a `202 Accepted` with a job ID immediately, allowing the client to poll for results.

*   **`KillController`**: [`src/main/java/com/aa/fso/controller/KillController.java:L19-19`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/controller/KillController.java#L19-19)
    *   **Behavior:** Endpoint to trigger the graceful shutdown of a running solver.
    *   **Safety:** Validates that the requested job ID matches the currently active run in `RunStateManager`.

---

## 7. Exception Handling Strategy

The module employs a centralized exception handling mechanism to ensure consistent API responses.

*   **`SolverException`**: [`src/main/java/com/aa/fso/exception/SolverException.java:L6-6`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/exception/SolverException.java#L6-6)
    *   **Usage:** Thrown when the optimization algorithm fails to find a feasible solution or encounters a mathematical error.
    *   **Handling:** Mapped to `500 Internal Server Error` with a detailed error message in the response body.

*   **`InvalidUserInputException`**:
    *   **Usage:** Thrown when input data violates schema or business logic constraints (e.g., invalid date range).
    *   **Handling:** Mapped to `400 Bad Request`.

*   **`KillRunException`**:
    *   **Usage:** Thrown internally when the `KillRun` signal is detected.
    *   **Handling:** Caught by the service layer to return a `200 OK` with a status message "Run Terminated by User".

*   **`SolverExceptionHandler`**: [`src/main/java/com/aa/fso/exception/SolverExceptionHandler.java:L16-16`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/exception/SolverExceptionHandler.java#L16-16)
    *   **Behavior:** Global `@ControllerAdvice` that catches all unchecked exceptions and converts them into standardized `MyErrorResponse` DTOs.

---

## 8. Configuration & Security

*   **`SecurityConfig`**: [`src/main/java/com/aa/fso/config/SecurityConfig.java:L16-16`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/config/SecurityConfig.java#L16-16)
    *   **Behavior:** Configures Spring Security to require OAuth2 Bearer tokens for all endpoints.
    *   **Integration:** Uses `ServicePrincipalAuthCallbackSB` to validate tokens issued by PingFederate.

*   **`AppProperties`**: [`src/main/java/com/aa/fso/properties/AppProperties.java:L14-14`](file:///Users/venkatesansubramanian/AntiGravityProjects/Sequence_Builder-6e0c87bc6e817c8c6919be50c1f325a806eb3d25/src/main/java/com/aa/fso/properties/AppProperties.java#L14-14)
    *   **Behavior:** Loads environment-specific configuration (Azure connection strings, Kafka brokers, solver timeouts) from `application.properties` or environment variables.

---

## 9. Summary of Workflow

1.  **Ingestion:** Client sends `SnapshotSolutionRequestInputDTO` to `HttpSolverController`.
2.  **Validation:** `InputValidationProcessor` checks data integrity.
3.  **Preparation:** `InputDataService` loads static data; `ConstructNetwork` builds the graph (`Network`, `Node`, `Edge`).
4.  **Optimization:**

---