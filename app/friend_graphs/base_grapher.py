
import time
import os
from datetime import datetime as dt
import pickle
import json

from dotenv import load_dotenv
from networkx import DiGraph, write_gpickle
from pandas import DataFrame

from app import APP_ENV, DATA_DIR
from app.decorators.datetime_decorators import logstamp
from app.decorators.number_decorators import fmt_n
from app.gcs_service import GoogleCloudStorageService

load_dotenv()

DRY_RUN = (os.getenv("DRY_RUN", default="true") == "true")
USERS_LIMIT = os.getenv("USERS_LIMIT")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", default=100))

class BaseGrapher():
    """
    Parent class with helper methods for assembling the graph object.

    Allows us to try various child class approaches to investigate and achieve memory optimization.

    Is able to write graph objects to file and upload them to Google Cloud Storage.

    Graph construction should be done in child class' perform() method.

    Example:
        grapher = BaseGrapher.cautiously_initialized()
        grapher.start()
        grapher.perform()
        grapher.end()
        grapher.report()
    """

    def __init__(self, dry_run=DRY_RUN, batch_size=BATCH_SIZE, users_limit=USERS_LIMIT, gcs_service=None, job_id=None):
        """
        Params:
            dry_run (bool)
                Whether or not to construct the graph object. If true, does not assemble the graph.

            users_limit (int / None)
                Optionally specifies the maximum number of users to fetch.
                If running into problems constructing a graph from the entire dataset,
                can just choose to create smaller graphs to get some kind of win.

            batch_size (int)
                When fetching from BigQuery, only determines the reporting interval.
                When fetching from PostgreSQL database via psycopg, determines number of users fetched from the database at once, and also the reporting interval.

            job_id (str / None)
                A unique identifer to associate a given job's results files.
                Is used as part of local filepaths and remote bucket paths, so should avoid including spaces or special characters.
                Assigns a timestamp-based unique identifier by default.
        """
        self.job_id = (job_id or dt.now().strftime("%Y-%m-%d-%H%M"))
        self.dry_run = (dry_run == True)
        self.batch_size = batch_size
        if users_limit:
            self.users_limit = int(users_limit)
        else:
            self.users_limit = None

        self.local_dirpath = os.path.join(DATA_DIR, "graphs", "archived", self.job_id)
        self.local_metadata_filepath = os.path.join(self.local_dirpath, "metadata.json")
        self.local_results_filepath = os.path.join(self.local_dirpath, "results.csv")
        self.local_edges_filepath = os.path.join(self.local_dirpath, "edges.gpickle")
        self.local_graph_filepath = os.path.join(self.local_dirpath, "graph.gpickle")

        self.gcs_service = (gcs_service or GoogleCloudStorageService())
        self.gcs_dirpath = os.path.join("storage", "data", "archived", self.job_id)
        self.gcs_metadata_filepath = os.path.join(self.gcs_dirpath, "metadata.json")
        self.gcs_results_filepath = os.path.join(self.gcs_dirpath, "results.csv")
        self.gcs_edges_filepath = os.path.join(self.gcs_dirpath, "edges.gpickle")
        self.gcs_graph_filepath = os.path.join(self.gcs_dirpath, "graph.gpickle")

    @classmethod
    def cautiously_initialized(cls):
        service = cls()
        print("-------------------------")
        print("GRAPHER CONFIG...")
        print("  JOB ID:", service.job_id)
        print("  DRY RUN:", str(service.dry_run).upper())
        print("  USERS LIMIT:", service.users_limit)
        print("  BATCH SIZE:", str(service.batch_size).upper())
        print("-------------------------")
        if APP_ENV == "development":
            if input("CONTINUE? (Y/N): ").upper() != "Y":
                print("EXITING...")
                exit()
        service.init_local_dir()
        return service

    def init_local_dir(self):
        if not os.path.exists(self.local_dirpath):
            os.mkdir(self.local_dirpath)

    @property
    def metadata(self):
        return {"app_env": APP_ENV, "job_id": self.job_id, "dry_run": self.dry_run, "batch_size": self.batch_size}

    def start(self):
        print("-----------------")
        print("JOB STARTING!")
        self.start_at = time.perf_counter()
        self.counter = 0

    def perform(self):
        """To be overridden by child class"""
        self.graph = DiGraph()

    def end(self):
        print("-----------------")
        print("JOB COMPLETE!")
        self.end_at = time.perf_counter()
        self.duration_seconds = round(self.end_at - self.start_at, 2)
        print(f"PROCESSED {fmt_n(self.counter)} USERS IN {fmt_n(self.duration_seconds)} SECONDS")

    def report(self):
        print("NODES:", fmt_n(len(self.graph.nodes)))
        print("EDGES:", fmt_n(len(self.graph.edges)))
        print("SIZE:", fmt_n(self.graph.size()))

    def write_metadata_to_file(self, metadata_filepath=None):
        metadata_filepath = metadata_filepath or self.local_metadata_filepath
        print(logstamp(), "WRITING METADATA...")
        with open(metadata_filepath, "w") as metadata_file:
            json.dump(self.metadata, metadata_file)

    def write_results_to_file(self, results_filepath=None):
        results_filepath = results_filepath or self.local_results_filepath
        print(logstamp(), "WRITING RESULTS...")
        df = DataFrame(self.running_results)
        df.to_csv(results_filepath)

    def write_edges_to_file(self, edges_filepath=None):
        edges_filepath = edges_filepath or self.local_edges_filepath
        print(logstamp(), "WRITING EDGES...:")
        with open(edges_filepath, "wb") as pickle_file:
            pickle.dump(self.edges, pickle_file)

    def write_graph_to_file(self, graph_filepath=None):
        graph_filepath = graph_filepath or self.local_graph_filepath
        print(logstamp(), "WRITING GRAPH...")
        write_gpickle(self.graph, graph_filepath)

    def upload_metadata(self):
        print(logstamp(), "UPLOADING JOB METADATA...", self.gcs_metadata_filepath)
        blob = self.gcs_service.upload(self.local_metadata_filepath, self.gcs_metadata_filepath)
        print(logstamp(), blob) #> <Blob: impeachment-analysis-2020, storage/data/2020-05-26-0002/metadata.json, 1590465770194318>

    def upload_results(self):
        print(logstamp(), "UPLOADING JOB RESULTS...", self.gcs_results_filepath)
        blob = self.gcs_service.upload(self.local_results_filepath, self.gcs_results_filepath)
        print(logstamp(), blob) #> <Blob: impeachment-analysis-2020, storage/data/2020-05-26-0002/metadata.json, 1590465770194318>

    def upload_edges(self):
        print(logstamp(), "UPLOADING NETWORK EDGES...", self.gcs_edges_filepath)
        blob = self.gcs_service.upload(self.local_edges_filepath, self.gcs_edges_filepath)
        print(logstamp(), blob)

    def upload_graph(self):
        print(logstamp(), "UPLOADING GRAPH...", self.gcs_graph_filepath)
        blob = self.gcs_service.upload(self.local_graph_filepath, self.gcs_graph_filepath)
        print(logstamp(), blob)

    def sleep(self):
        if APP_ENV == "production":
            print("SLEEPING...")
            time.sleep(12 * 60 * 60) # twelve hours, more than enough time to stop the server

if __name__ == "__main__":


    #grapher = BaseGrapher(job_id="2020-05-27-1537")
    #grapher.upload_edges()

    grapher = BaseGrapher.cautiously_initialized()
    grapher.start()
    grapher.perform()
    grapher.end()
    grapher.report()
