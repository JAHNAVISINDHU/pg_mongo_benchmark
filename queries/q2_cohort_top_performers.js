// Query 2: Top 10 Users by Event Count Within Their Signup-Month Cohort
// Leverages denormalized cohort_month on each event document (no $lookup needed)
// Uses $setWindowFields with $rank

db.events.aggregate([
  {
    "$group": {
      "_id": { "cohort_month": "$cohort_month", "user_id": "$user_id" },
      "event_count": { "$sum": 1 }
    }
  },
  {
    "$setWindowFields": {
      "partitionBy": "$_id.cohort_month",
      "sortBy": { "event_count": -1 },
      "output": {
        "rank": { "$rank": {} }
      }
    }
  },
  { "$match": { "rank": { "$lte": 10 } } },
  {
    "$project": {
      "_id": 0,
      "cohort_month": "$_id.cohort_month",
      "user_id":      "$_id.user_id",
      "event_count":  1,
      "rank":         1
    }
  },
  { "$sort": { "cohort_month": 1, "rank": 1 } }
], { "allowDiskUse": true })
