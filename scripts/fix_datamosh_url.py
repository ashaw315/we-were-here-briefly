import os
import psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.getenv('POSTGRES_URL'))
cur = conn.cursor()

datamosh_url = 'https://pub-dfd09c6a5bcd43dda4ed449bb2e01d95.r2.dev/datamosh.mp4'

cur.execute(
    "UPDATE runs SET datamosh_url = %s WHERE datamosh_url IS NULL",
    (datamosh_url,)
)

print(f"Updated {cur.rowcount} rows")
conn.commit()
cur.close()
conn.close()
