/**
 * Vercel serverless function — serves run metadata from Postgres.
 *
 * Routes:
 *   GET /api/runs         → all runs (newest first)
 *   GET /api/runs?latest  → single most recent run
 *
 * Connects to Vercel Postgres using the POSTGRES_URL env var
 * that Vercel auto-populates when you link a database.
 *
 * No authentication — this data is public.
 */

// pg is the standard Node.js Postgres client.
// Vercel's Node.js runtime includes it by default when you
// have a linked Postgres database, or you can add it via package.json.
const { Pool } = require("pg");

// Pool manages a set of reusable database connections.
// connectionString comes from the POSTGRES_URL env var.
// ssl: { rejectUnauthorized: false } is needed for Vercel Postgres.
const pool = new Pool({
  connectionString: process.env.POSTGRES_URL,
  ssl: { rejectUnauthorized: false },
});

module.exports = async function handler(req, res) {
  // Only allow GET requests
  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  try {
    // ?latest query param returns just the most recent run
    const isLatest = "latest" in req.query;

    let query;
    if (isLatest) {
      query = `
        SELECT id, date, seed, sentence, video_url,
               datamosh_url, style_mode, created_at
        FROM runs
        ORDER BY created_at DESC
        LIMIT 1
      `;
    } else {
      query = `
        SELECT id, date, seed, sentence, video_url,
               datamosh_url, style_mode, created_at
        FROM runs
        ORDER BY created_at DESC
      `;
    }

    const result = await pool.query(query);

    // Format dates as ISO strings for JSON serialization.
    // Postgres DATE type comes back as a JS Date object.
    const rows = result.rows.map((row) => ({
      ...row,
      date: row.date instanceof Date
        ? row.date.toISOString().split("T")[0]
        : row.date,
      created_at: row.created_at instanceof Date
        ? row.created_at.toISOString()
        : row.created_at,
    }));

    // Cache for 60 seconds — data only changes once per day
    res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=300");

    if (isLatest) {
      // Return single object (or 404 if no runs)
      if (rows.length === 0) {
        return res.status(404).json({ error: "No runs found" });
      }
      return res.status(200).json(rows[0]);
    }

    // Return array of all runs
    return res.status(200).json(rows);
  } catch (error) {
    console.error("Database error:", error.message);
    return res.status(500).json({ error: "Database error" });
  }
};
