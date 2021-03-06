
import pickle

from networkx import DiGraph
from memory_profiler import profile

from app.decorators.datetime_decorators import logstamp
from app.decorators.number_decorators import fmt_n
from app.friend_graphs.bq_grapher import BigQueryGrapher

class BigQueryListGrapher(BigQueryGrapher):

    @profile
    def perform(self):
        self.start()
        self.write_metadata_to_file()
        self.upload_metadata()

        self.edges = []
        self.running_results = []
        for row in self.bq_service.fetch_user_friends_in_batches(limit=self.users_limit):
            self.counter += 1

            if not self.dry_run:
                self.edges += [(row["screen_name"], friend) for friend in row["friend_names"]]

            if self.counter % self.batch_size == 0:
                rr = {"ts": logstamp(), "counter": self.counter, "edges": len(self.edges)}
                print(rr["ts"], "|", fmt_n(rr["counter"]), "|", fmt_n(rr["edges"]))
                self.running_results.append(rr)

        self.write_results_to_file()
        self.upload_results()

        self.write_edges_to_file()
        self.upload_edges()

        print(logstamp(), "CONSTRUCTING GRAPH OBJECT...")
        self.graph = DiGraph(self.edges)
        print(logstamp(), "GRAPH CONSTRUCTED!")
        self.report()

        del self.running_results # remove in hopes of freeing up some memory
        del self.edges # remove in hopes of freeing up some memory

        self.write_graph_to_file()
        #del self.graph # remove in hopes of freeing up some memory
        self.upload_graph()

        self.end()

    def write_edges_to_file(self):
        """
        overwrite the parent method because we need self.edges vs self.graph.edges
        todo: inherit / mix-in
        """
        print(logstamp(), "WRITING EDGES...:")
        with open(self.local_edges_filepath, "wb") as pickle_file:
            pickle.dump(self.edges, pickle_file) # write edges before graph is constructed

if __name__ == "__main__":

    grapher = BigQueryListGrapher.cautiously_initialized()

    grapher.perform()

    grapher.sleep()
