"""CLI entry point."""
from .company import get_company
from .graph_query import build_graph
from .intelligence import analyze_graph


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("company")
    args=p.parse_args()
    company=get_company(args.company)
    graph=build_graph(company)
    print(analyze_graph(graph))


if __name__=="__main__":
    main()
