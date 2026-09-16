"""Job's final task: future Gold -> Cosmos projection, never a pipeline input.

TODO: read approved Gold outputs, project only app-facing fields, and upsert
using the team's container/partition/id contracts and managed secrets.
No team business schema or Cosmos credential is assumed by this scaffold.
"""


def main():
    raise NotImplementedError(
        "Weekly analysis is a scaffold. Team transformations and Gold-to-Cosmos "
        "projection must be connected before enabling this Job. Nothing was published."
    )


if __name__ == "__main__":
    main()
