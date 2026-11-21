"""Keep list context across workspace forms without accepting redirect targets."""

from urllib.parse import parse_qsl, urlsplit

from flask import request, url_for

LIST_FILTERS = {"q", "course", "role", "teacher", "record", "sort", "page"}


def listing_link(endpoint, listing, **route):
    filters = {key: value for key, value in listing.filters.items() if value}
    if listing.page > 1:
        filters["page"] = listing.page
    return url_for(endpoint, **route, **filters)


def listing_return(endpoint, **route):
    """Rebuild a URL for the expected listing with only its query state."""
    fallback = url_for(endpoint, **route)
    raw = request.args.get("return_to", "")
    if not raw or len(raw) > 2048:
        return fallback
    try:
        target = urlsplit(raw)
        if target.scheme or target.netloc or target.fragment or target.path != fallback:
            return fallback
        filters = {key: value for key, value in parse_qsl(target.query, max_num_fields=12)
                   if key in LIST_FILTERS and len(value) <= 100}
    except ValueError:
        return fallback
    return url_for(endpoint, **route, **filters)
