// Power Query (M) for the three Dataverse tables, plus one parameter.
// Get data → Dataverse, enter your environment host, pick the tables, then click Transform data.
// Replace each query's Advanced Editor contents with the ones below.
// Keeping only the needed columns is the #1 performance lever. A Dataverse table has
// dozens of system columns that would otherwise bloat the model.

// ---------- Parameter: ReportingUtcOffsetHours ----------
// Manage parameters → New. Type: Decimal number. Dataverse returns every date-time in UTC.
// Without a shift, a request submitted at 8 pm Eastern lands on the next day's bar.
// A fixed offset is off by one hour for half the year (daylight saving); that only moves
// requests made in the hour around midnight, which is an acceptable error for a daily chart.
-5 meta [IsParameterQuery = true, Type = "Number", IsParameterQueryRequired = true]

// ---------- Query: Training Request (fact) ----------
let
    Source   = CommonDataService.Database("<org>.crm.dynamics.com"),
    Requests = Source{[Schema = "dbo", Item = "jc_trainingrequest"]}[Data],
    Kept     = Table.SelectColumns(Requests, {
                   "jc_trainingrequestid", "jc_title", "jc_course", "ownerid",
                   "jc_requeststatusname",               // choice label (the number is jc_requeststatus)
                   "jc_pendingwith",
                   "jc_submittedon", "jc_decisiondate", "jc_completedon", "jc_coursecost"
               }),
    Renamed  = Table.RenameColumns(Kept, {
                   {"jc_trainingrequestid", "Request ID"}, {"jc_title", "Title"},
                   {"jc_course", "Course ID"}, {"ownerid", "Requester ID"},
                   {"jc_requeststatusname", "Request Status"}, {"jc_pendingwith", "Pending With"},
                   {"jc_submittedon", "Submitted On"}, {"jc_decisiondate", "Decision Date"},
                   {"jc_completedon", "Completed On"}, {"jc_coursecost", "Course Cost"}
               }),
    Typed    = Table.TransformColumnTypes(Renamed, {
                   {"Requester ID", type text}, {"Course ID", type text},
                   {"Submitted On", type datetime}, {"Decision Date", type datetime},
                   {"Completed On", type datetime}, {"Course Cost", Currency.Type}
               }),
    // UTC → reporting time zone. Applied to all three so durations between them are unchanged.
    Shift    = (utc as nullable datetime) as nullable datetime =>
                   if utc = null then null else utc + #duration(0, ReportingUtcOffsetHours, 0, 0),
    Local    = Table.TransformColumns(Typed, {
                   {"Submitted On", Shift, type datetime}, {"Decision Date", Shift, type datetime},
                   {"Completed On", Shift, type datetime}
               }),
    // Date-only keys for the Date table relationships (datetime columns can't join to a date table cleanly).
    AddSubmittedDate = Table.AddColumn(Local, "Submitted Date",
                   each if [Submitted On] = null then null else DateTime.Date([Submitted On]), type date),
    AddDecisionDate  = Table.AddColumn(AddSubmittedDate, "Decision Day",
                   each if [Decision Date] = null then null else DateTime.Date([Decision Date]), type date)
in
    AddDecisionDate

// ---------- Query: Training Course (dimension) ----------
let
    Source  = CommonDataService.Database("<org>.crm.dynamics.com"),
    Courses = Source{[Schema = "dbo", Item = "jc_trainingcourse"]}[Data],
    Kept    = Table.SelectColumns(Courses, {
                  "jc_trainingcourseid", "jc_name", "jc_provider",
                  "jc_categoryname", "jc_cost", "jc_hours", "jc_active"
              }),
    Renamed = Table.RenameColumns(Kept, {
                  {"jc_trainingcourseid", "Course ID"}, {"jc_name", "Course"},
                  {"jc_provider", "Provider"}, {"jc_categoryname", "Category"},
                  {"jc_cost", "Cost"}, {"jc_hours", "Hours"}, {"jc_active", "Active"}
              }),
    Typed   = Table.TransformColumnTypes(Renamed, {
                  {"Course ID", type text}, {"Cost", Currency.Type}, {"Hours", Int64.Type}
              })
in
    Typed

// ---------- Query: Requester (dimension, and the basis for row-level security) ----------
// Every user, including disabled ones and people who never made a request: the manager
// hierarchy in rls.dax needs each manager to exist as a row.
let
    Source  = CommonDataService.Database("<org>.crm.dynamics.com"),
    Users   = Source{[Schema = "dbo", Item = "systemuser"]}[Data],
    Kept    = Table.SelectColumns(Users, {
                  "systemuserid", "fullname", "domainname", "parentsystemuserid"
              }),
    Renamed = Table.RenameColumns(Kept, {
                  {"systemuserid", "User ID"}, {"fullname", "Requester"},
                  {"domainname", "UPN"}, {"parentsystemuserid", "Manager ID"}
              }),
    Typed   = Table.TransformColumnTypes(Renamed, {
                  {"User ID", type text}, {"Manager ID", type text}, {"UPN", type text}
              })
in
    Typed
