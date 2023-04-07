import datetime
from enum import Enum
from typing import Dict

import pytest
from dataclasses import dataclass, fields, Field

from golem_core.demand_builder.model import (
    Model,
    prop,
    constraint,
    InvalidPropertiesError,
    join_str_constraints,
    ConstraintException,
)

