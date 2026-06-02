"""Request/Response adapter protocols for framework independence.

Provides protocols for adapting framework-specific request/response objects
to framework-agnostic GenericRequest/GenericResponse.

[INPUT]
- channels.protocols.route_registrar::GenericRequest, (POS: Protocol layer for dynamic HTTP route registration. Enables channels to declare their own HTTP endpoints while maintaining framework independence. Business layer implements RouteRegistrar for a specific web framework (e.g. FastAPI via ``myrm-agent-harness[fastapi]``).)

[OUTPUT]
- RequestAdapter Protocol: Adapts framework-specific request to GenericRequest
- ResponseAdapter Protocol: Adapts GenericResponse to framework-specific response

[POS]
Adapter layer for framework independence. Business layer implements these
protocols for specific web frameworks (e.g. FastAPI). Channels
receive GenericRequest and return GenericResponse, remaining framework-agnostic.
"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

from app.channels.protocols.route_registrar import (
    GenericRequest,
    GenericResponse,
)

TRequest = TypeVar("TRequest", contravariant=True)
TResponse = TypeVar("TResponse", covariant=True)


class RequestAdapter(Protocol, Generic[TRequest]):
    """Protocol for adapting framework-specific request to GenericRequest.

    Business layer implements this protocol for each web framework
    (e.g. FastAPI) to convert framework-specific request
    objects to the generic interface.

    Example:
        class FastAPIRequestAdapter(RequestAdapter[Request]):
            def adapt(self, request: Request) -> GenericRequest:
                # Convert FastAPI Request to GenericRequest
                ...
    """

    def adapt(self, request: TRequest) -> GenericRequest:
        """Adapt framework-specific request to GenericRequest.

        Args:
            request: Framework-specific request object

        Returns:
            GenericRequest interface compatible object
        """
        ...


class ResponseAdapter(Protocol, Generic[TResponse]):
    """Protocol for adapting GenericResponse to framework-specific response.

    Business layer implements this protocol for each web framework
    (e.g. FastAPI) to convert GenericResponse to framework-specific
    response objects.

    Example:
        class FastAPIResponseAdapter(ResponseAdapter[Response]):
            def adapt(self, response: GenericResponse) -> Response:
                # Convert GenericResponse to FastAPI Response
                ...
    """

    def adapt(self, response: GenericResponse) -> TResponse:
        """Adapt GenericResponse to framework-specific response.

        Args:
            response: GenericResponse interface compatible object

        Returns:
            Framework-specific response object
        """
        ...
