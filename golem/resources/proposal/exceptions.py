from typing import TYPE_CHECKING, Optional

from golem.resources.exceptions import ResourceException

if TYPE_CHECKING:
    from golem.resources import ProposalId


class ProposalException(ResourceException):
    pass


class ProposalRejected(ResourceException):
    def __init__(self, proposal_id: Optional["ProposalId"], reason: str):
        self._proposal_id = proposal_id
        self._reason = reason

        super().__init__(f"Proposal `{proposal_id}` rejected! Reason: `{reason}`")

    @property
    def proposal_id(self) -> Optional["ProposalId"]:
        return self._proposal_id

    @property
    def reason(self) -> str:
        return self._reason
