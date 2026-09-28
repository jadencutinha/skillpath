// Power Query (M) for the two Dataverse tables.
// Get data → Dataverse, enter your environment host, pick the tables, then click Transform data.
// Replace each query's Advanced Editor contents with the ones below.
// Keeping only the needed columns is the #1 performance lever. A Dataverse table has
// dozens of system columns that would otherwise bloat the model.

// ---------- Query: Training Request (fact) ----------
let
    Source   = CommonDataService.Database("<org>.crm.dynamics.com"),
    Requests = Source{[Schema = "dbo", Item = "jc_trainingrequest"]}[Data],
    Kept     = Table.SelectColumns(Requests, {
                   "jc_trainingrequestid", "jc_title", "jc_course",
                   "jc_requeststatusname",               // choice label (the number is jc_requeststatus)
                   "jc_submittedon", "jc_decisiondate", "jc_coursecost",
                   "owneridname"
               }),
    Renamed  = Table.RenameColumns(Kept, {
                   {"jc_trainingrequestid", "Request ID"}, {"jc_title", "Title"},
                   {"jc_course", "Course ID"}, {"jc_requeststatusname", "Request Status"},
                   {"jc_submittedon", "Submitted On"}, {"jc_decisiondate", "Decision Date"},
                   {"jc_coursecost", "Course Cost"}, {"owneridname", "Requester"}
               }),
    Typed    = Table.TransformColumnTypes(Renamed, {
                   {"Submitted On", type datetime}, {"Decision Date", type datetime},
                   {"Course Cost", Currency.Type}
               }),
    // Date-only keys for the Date table relationships (datetime columns can't join to a date table cleanly).
    AddSubmittedDate = Table.AddColumn(Typed, "Submitted Date",
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
    Typed   = Table.TransformColumnTypes(Renamed, {{"Cost", Currency.Type}, {"Hours", Int64.Type}})
in
    Typed
