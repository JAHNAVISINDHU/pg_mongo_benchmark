// Query 3: First and Last Event Timestamp for Every User
// Uses compound index { user_id: 1, created_at: -1 } → IXSCAN
// executionStats should show: nReturned ≈ totalDocsExamined

db.events.aggregate([
  {
    "$group": {
      "_id": "$user_id",
      "first_event": { "$min": "$created_at" },
      "last_event":  { "$max": "$created_at" }
    }
  },
  { "$sort": { "_id": 1 } }
], { "allowDiskUse": true })
