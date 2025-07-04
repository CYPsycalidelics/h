"""
HTTP/REST API for storage and retrieval of annotation data.

This module contains the views which implement our REST API, mounted by default
at ``/api``. Currently, the endpoints are limited to:

- basic CRUD (create, read, update, delete) operations on annotations
- annotation search
- a handful of authentication related endpoints

It is worth noting up front that in general, authorization for requests made to
each endpoint is handled outside of the body of the view functions. In
particular, requests to the CRUD API endpoints are protected by the Pyramid
authorization system. You can find the mapping between annotation "permissions"
objects and Pyramid ACLs in :mod:`h.traversal`.
"""

from pyramid import i18n
from pyramid.httpexceptions import HTTPNotFound

from h import search as search_lib
from h.events import AnnotationEvent
from h.presenters import AnnotationJSONLDPresenter
from h.schemas.annotation import (
    CreateAnnotationSchema,
    SearchParamsSchema,
    UpdateAnnotationSchema,
)
from h.schemas.util import validate_query_params
from h.security import Permission
from h.services import AnnotationWriteService
from h.views.api.config import api_config
from h.views.api.helpers.json_payload import json_payload

_ = i18n.TranslationStringFactory(__package__)


@api_config(
    versions=["v1", "v2"],
    route_name="api.search",
    link_name="search",
    description="Search for annotations",
)
def search(request):
    """Search the database for annotations matching with the given query."""
    schema = SearchParamsSchema()
    params = validate_query_params(schema, request.params)

    separate_replies = params.pop("_separate_replies", False)

    result = search_lib.Search(request, separate_replies=separate_replies).run(params)

    svc = request.find_service(name="annotation_json")

    out = {
        "total": result.total,
        "rows": svc.present_all_for_user(
            annotation_ids=result.annotation_ids, user=request.user
        ),
    }

    if separate_replies:
        out["replies"] = svc.present_all_for_user(
            annotation_ids=result.reply_ids, user=request.user
        )

    return out


@api_config(
    versions=["v1", "v2"],
    route_name="api.annotations",
    request_method="POST",
    permission=Permission.Annotation.CREATE,
    link_name="annotation.create",
    description="Create an annotation",
)
def create(request):
    """Create an annotation from the POST payload."""
    schema = CreateAnnotationSchema(request)
    appstruct = schema.validate(json_payload(request))

    annotation = request.find_service(AnnotationWriteService).create_annotation(
        data=appstruct
    )

    _publish_annotation_event(request, annotation, "create")

    return request.find_service(name="annotation_json").present_for_user(
        annotation=annotation, user=request.user
    )


@api_config(
    versions=["v1", "v2"],
    route_name="api.annotation",
    request_method="GET",
    permission=Permission.Annotation.READ,
    link_name="annotation.read",
    description="Fetch an annotation",
)
def read(context, request):
    """Return the annotation (simply how it was stored in the database)."""
    return request.find_service(name="annotation_json").present_for_user(
        annotation=context.annotation, user=request.user
    )


@api_config(
    versions=["v1", "v2"],
    route_name="api.annotation.jsonld",
    request_method="GET",
    permission=Permission.Annotation.READ,
)
def read_jsonld(context, request):
    request.response.content_type = "application/ld+json"
    request.response.content_type_params = {
        "charset": "UTF-8",
        "profile": str(AnnotationJSONLDPresenter.CONTEXT_URL),
    }

    return AnnotationJSONLDPresenter(
        context.annotation, links_service=request.find_service(name="links")
    ).asdict()


@api_config(
    versions=["v1", "v2"],
    route_name="api.annotation",
    request_method=("PATCH", "PUT"),
    permission=Permission.Annotation.UPDATE,
    link_name="annotation.update",
    description="Update an annotation",
)
def update(context, request):
    """Update the specified annotation with data from the PATCH payload."""
    schema = UpdateAnnotationSchema(
        request, context.annotation.target_uri, context.annotation.groupid
    )
    appstruct = schema.validate(json_payload(request))

    annotation = request.find_service(AnnotationWriteService).update_annotation(
        context.annotation, data=appstruct
    )

    _publish_annotation_event(request, annotation, "update")

    return request.find_service(name="annotation_json").present_for_user(
        annotation=annotation, user=request.user
    )


@api_config(
    versions=["v1", "v2"],
    route_name="api.annotation",
    request_method="DELETE",
    permission=Permission.Annotation.DELETE,
    link_name="annotation.delete",
    description="Delete an annotation",
)
def delete(context, request):
    """Delete the specified annotation."""
    annotation_delete_service = request.find_service(name="annotation_delete")
    annotation_delete_service.delete(context.annotation)

    # TODO: Track down why we don't return an HTTP 204 like other DELETEs  # noqa: FIX002, TD002, TD003
    return {"id": context.annotation.id, "deleted": True}


@api_config(
    versions=["v1", "v2"],
    route_name="api.annotation.reindex",
    request_method="POST",
    link_name="annotation.reindex",
    description="Reindex an annotation",
)
def reindex(context, request):
    """
    Reindex one particular annotation.

    The main motivation for this endpoint is to support
    the functional tests, which often need to make sure an annotation
    created in the DB is up to date in ES.
    """
    if not request.registry.settings["h.dev"]:
        # Don't allow reindexing in production
        raise HTTPNotFound

    search_index = request.find_service(name="search_index")
    search_index.add_annotation(context.annotation, refresh=True)

    return {"id": context.annotation.id, "indexed": True}


def _publish_annotation_event(request, annotation, action):
    """Publish an event to the annotations queue for this annotation action."""
    event = AnnotationEvent(request, annotation.id, action)
    request.notify_after_commit(event)
