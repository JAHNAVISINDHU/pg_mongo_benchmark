// Query 5: Revenue Contribution — Each Purchase as % of User's Lifetime Spend
// Uses $setWindowFields with unbounded window for lifetime sum

db.events.aggregate([
  { "$match": { "event_type": "purchase" } },
  {
    "$setWindowFields": {
      "partitionBy": "$user_id",
      "sortBy": { "created_at": 1 },
      "output": {
        "lifetime_spend": {
          "$sum": "$payload.amount",
          "window": { "documents": ["unbounded", "unbounded"] }
        }
      }
    }
  },
  {
    "$addFields": {
      "purchase_amount": "$payload.amount",
      "pct_of_lifetime": {
        "$cond": [
          { "$eq": ["$lifetime_spend", 0] },
          0,
          {
            "$round": [
              { "$multiply": [
                { "$divide": ["$payload.amount", "$lifetime_spend"] },
                100
              ]},
              6
            ]
          }
        ]
      }
    }
  },
  {
    "$project": {
      "_id":             0,
      "user_id":         1,
      "purchase_amount": 1,
      "lifetime_spend":  { "$round": ["$lifetime_spend", 4] },
      "pct_of_lifetime": 1,
      "created_at":      1
    }
  },
  { "$sort": { "user_id": 1, "created_at": 1 } }
], { "allowDiskUse": true })
