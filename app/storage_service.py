from datetime import datetime
import os
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") # implicit check by google.cloud (and keras)
PROJECT_NAME = os.getenv("BIGQUERY_PROJECT_NAME", default="tweet-collector-py")
DATASET_NAME = os.getenv("BIGQUERY_DATASET_NAME", default="impeachment_development") #> "_test" or "_production"

class BigQueryService():
    """
    See:
        https://cloud.google.com/bigquery/docs/reference/standard-sql/operators
        https://cloud.google.com/bigquery/docs/reference/standard-sql/conversion_rules
    """

    def __init__(self, project_name=PROJECT_NAME, dataset_name=DATASET_NAME, init_tables=False):
        self.project_name = project_name
        self.dataset_name = dataset_name
        self.dataset_address = f"{self.project_name}.{self.dataset_name}"

        self.client = bigquery.Client()
        self.dataset_ref = self.client.dataset(self.dataset_name)
        if init_tables == True:
            self.init_tables()

    def init_tables(self):
        """ Creates new tables for storing follower graphs """
        self.migrate_populate_users()
        self.migrate_user_friends()
        user_friends_table_ref = self.dataset_ref.table("user_friends")
        self.user_friends_table = self.client.get_table(user_friends_table_ref) # an API call (caches results for subsequent inserts)

    def migrate_populate_users(self):
        sql = f"""
            CREATE TABLE IF NOT EXISTS {self.dataset_address}.users as (
                SELECT distinct(user_id) as user_id
                FROM `{self.dataset_address}.tweets`
                ORDER BY 1
            );
        """
        results = self.execute_query(sql)
        return list(results)

    def migrate_user_friends(self):
        # see: https://cloud.google.com/bigquery/docs/reference/standard-sql/data-types#array-type
        # f"DROP TABLE IF EXISTS `{self.dataset_address}.user_friends`;"
        sql = f"""
            CREATE TABLE IF NOT EXISTS `{self.dataset_address}.user_friends` (
                user_id STRING,
                friends_count INT64,
                friend_ids ARRAY<STRING>
            );
        """
        results = self.execute_query(sql)
        return list(results)

    def execute_query(self, sql):
        """Param: sql (str)"""
        job = self.client.query(sql)
        return job.result()

    def fetch_remaining_users(self, min_id=None, max_id=None, limit=None):
        """Returns a list of table rows"""
        sql = f"""
            SELECT
                u.user_id
            FROM `{self.dataset_address}.users` u
            LEFT JOIN `{self.dataset_address}.user_friends` f ON u.user_id = f.user_id
            WHERE f.user_id IS NULL
        """
        if min_id and max_id:
            sql += f"  AND CAST(u.user_id as int64) BETWEEN {int(min_id)} AND {int(max_id)} "
            sql += f"ORDER BY u.user_id;"
        elif limit:
            sql += f"ORDER BY u.user_id "
            sql += f"LIMIT {limit};"
        else:
            sql += f"ORDER BY u.user_id;"
        print(sql)
        results = self.execute_query(sql)
        return list(results)

    def append_user_friends(self, records):
        """Param: records (list of dictionaries)"""
        rows_to_insert = [list(d.values()) for d in records]
        errors = self.client.insert_rows(self.user_friends_table, rows_to_insert)
        return errors

if __name__ == "__main__":

    service = BigQueryService()
    print("BIGQUERY DATASET:", service.dataset_address.upper())

    if input("CONTINUE? (Y/N): ").upper() != "Y":
        print("EXITING...")
        exit()

    #print("--------------------")
    #print("FETCHING TOPICS...")
    #sql = f"""
    #    SELECT topic, created_at
    #    FROM `{self.dataset_address}.topics`
    #    ORDER BY created_at;
    #"""
    #results = service.execute_query(sql)
    #for row in results:
    #    print(row)
    #    print("---")

    print("--------------------")
    #print("COUNTING TWEETS AND USERS...")
    sql = f"""
        SELECT
            count(distinct status_id) as tweet_count
            ,count(distinct user_id) as user_count
        FROM `{service.dataset_address}.tweets`
    """
    results = service.execute_query(sql)
    first_row = list(results)[0]
    user_count = first_row.user_count
    print(f"TWEETS: {first_row.tweet_count:,}") # formatting with comma separators for large numbers
    print(f"USERS: {user_count:,}") # formatting with comma separators for large numbers

    #print("--------------------")
    #print("FETCHING LATEST TWEETS...")
    #sql = f"""
    #    SELECT
    #        status_id, status_text, geo, created_at,
    #        user_id, user_screen_name, user_description, user_location, user_verified
    #    FROM `{service.dataset_address}.tweets`
    #    ORDER BY created_at DESC
    #    LIMIT 3
    #"""
    #results = service.execute_query(sql)
    #for row in results:
    #    print(row)
    #    print("---")

    service.init_tables()

    print("--------------------")
    #print("COUNTING USER FRIEND GRAPHS...")
    sql = f"""
        SELECT count(distinct user_id) as user_count
        FROM `{service.dataset_address}.user_friends`
    """
    results = service.execute_query(sql)
    graphed_user_count = list(results)[0].user_count
    print("USERS WITH FRIEND GRAPHS:", graphed_user_count)
    percent_collected = graphed_user_count / user_count
    print(f"{(percent_collected * 100):.1f}% COLLECTED")
    print(f"{((1 - percent_collected) * 100):.1f}% REMAINING")
