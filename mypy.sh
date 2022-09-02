#   Most of the --strict flags are included
mypy \
    --namespace-packages            \
    --install-types                 \
    low_example.py                  \
    mid_example.py                  \
    golem_api                       \
    --warn-unused-configs           \
    --disallow-incomplete-defs      \
    --disallow-subclassing-any      \
    --disallow-untyped-decorators   \
    --no-implicit-optional          \
    --warn-redundant-casts          \
    --warn-unused-ignores           \
    --warn-return-any               \
    --strict-equality               \
    --strict-concatenate            \
    --check-untyped-defs            \
    --disallow-untyped-defs         \

    #   Disabled parts of --strict
    # --disallow-any-generics         \
    # --no-implicit-reexport          \
    # --disallow-untyped-calls        \
