// Query 1: 7-Day Rolling Average Revenue per Day
// Uses $setWindowFields with $avg window operator

db.events.aggregate([
  {
    "$match": { "event_type": "purchase" }
  },
  {
    "$group": {
      "_id": {
        "$dateToString": { "format": "%Y-%m-%d", "date": "$created_at" }
      },
      "avg_amount": { "$avg": "$payload.amount" }
    }
  },
  { "$sort": { "_id": 1 } },
  {
    "$setWindowFields": {
      "sortBy": { "_id": 1 },
      "output": {
        "rolling_7d_avg": {
          "$avg": "$avg_amount",
          "window": { "documents": [-6, "current"] }
        }
      }
    }
  },
  {
    "$project": {
      "_id": 0,
      "day": "$_id",
      "daily_avg_amount": { "$round": ["$avg_amount", 4] },
      "rolling_7d_avg":   { "$round": ["$rolling_7d_avg", 4] }
    }
  }
])
