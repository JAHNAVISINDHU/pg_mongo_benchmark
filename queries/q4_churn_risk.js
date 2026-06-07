// Query 4: Churn Risk — Users Whose Session Count Declined Last 7 Days vs Prior 7 Days
// Two-pass pipeline on the sessions collection

// Pass 1: find the global max start_time
var refDoc = db.sessions.aggregate([
  { "$group": { "_id": null, "max_dt": { "$max": "$start_time" } } }
]).toArray()[0];

var refDate    = refDoc.max_dt;
var day7ago    = new Date(refDate - 7  * 24 * 3600 * 1000);
var day14ago   = new Date(refDate - 14 * 24 * 3600 * 1000);

// Pass 2: facet last-7 and prev-7 counts, then diff
db.sessions.aggregate([
  {
    "$facet": {
      "last7": [
        { "$match": { "start_time": { "$gte": day7ago } } },
        { "$group": { "_id": "$user_id", "cnt": { "$sum": 1 } } }
      ],
      "prev7": [
        { "$match": { "start_time": { "$gte": day14ago, "$lt": day7ago } } },
        { "$group": { "_id": "$user_id", "cnt": { "$sum": 1 } } }
      ]
    }
  },
  { "$unwind": "$last7" },
  {
    "$lookup": {
      "from":         "sessions",
      "localField":   "last7._id",
      "foreignField": "_id",
      "as":           "_ignored"
    }
  }
], { "allowDiskUse": true })
