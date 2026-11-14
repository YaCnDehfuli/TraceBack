"""Database-side rules: the memories validator and every index (guide 8.7).

The validator is what makes "Memory refused: no proof" real: Atlas rejects any
memory whose verification didn't fail before and pass after.
"""
from __future__ import annotations

from pymongo import ASCENDING

from core.config import get_settings

EMBEDDING_DIMS = get_settings().embedding_dimensions

MEMORY_VALIDATOR = {
    "$and": [
        {
            "$jsonSchema": {
                "bsonType": "object",
                "required": [
                    "tenantId", "ownerTeamId", "readableBy", "repositoryId", "status",
                    "version", "lineageId", "expiresAt", "purgeAt", "provenance",
                    "verification", "embedding", "embeddingVersion", "hmacSecret",
                ],
                "properties": {
                    "status": {"enum": ["active", "disputed", "superseded", "revoked"]},
                    "readableBy": {"bsonType": "array", "minItems": 1, "items": {"bsonType": "string"}},
                    "expiresAt": {"bsonType": "date"},
                    "purgeAt": {"bsonType": "date"},
                    "verification": {
                        "bsonType": "object",
                        "required": ["runId", "status", "beforeFailed", "afterPassed", "evidenceHashes"],
                        "properties": {
                            # Same rule as VerificationResult.verified, enforced by Atlas.
                            "status": {"enum": ["passed"]},
                            "beforeFailed": {"enum": [True]},
                            "afterPassed": {"enum": [True]},
                        },
                    },
                    "embedding": {
                        "bsonType": "array",
                        "minItems": EMBEDDING_DIMS,
                        "maxItems": EMBEDDING_DIMS,
                    },
                },
            }
        },
        {"$expr": {"$in": ["$ownerTeamId", "$readableBy"]}},
    ]
}

VECTOR_INDEX_DEFINITION = {
    "fields": [
        {"type": "vector", "path": "embedding", "numDimensions": EMBEDDING_DIMS, "similarity": "cosine"},
        {"type": "filter", "path": "tenantId"},
        {"type": "filter", "path": "readableBy"},
        {"type": "filter", "path": "repositoryId"},
        {"type": "filter", "path": "status"},
        {"type": "filter", "path": "expiresAt"},
        {"type": "filter", "path": "embeddingVersion"},
    ]
}

# collection -> list of (keys, options)
INDEXES: dict[str, list[tuple[list, dict]]] = {
    "memories": [
        ([("purgeAt", ASCENDING)], {"name": "purge_ttl", "expireAfterSeconds": 0}),
        (
            [("tenantId", ASCENDING), ("provenance.sourceIncidentId", ASCENDING),
             ("provenance.sourceRevision", ASCENDING), ("version", ASCENDING)],
            {"name": "promote_once", "unique": True},
        ),
        ([("lineageId", ASCENDING), ("version", ASCENDING)], {"name": "lineage"}),
        ([("tenantId", ASCENDING), ("signature.errorCode", ASCENDING), ("signature.operation", ASCENDING)],
         {"name": "signature"}),
    ],
    "memory_audit": [
        ([("memoryId", ASCENDING), ("at", ASCENDING)], {"name": "by_memory"}),
        ([("tenantId", ASCENDING), ("actor.id", ASCENDING), ("at", ASCENDING)], {"name": "by_actor"}),
    ],
    "runs": [
        ([("tenantId", ASCENDING), ("idempotencyKey", ASCENDING)],
         {"name": "idempotency", "unique": True, "partialFilterExpression": {"idempotencyKey": {"$type": "string"}}}),
        ([("status", ASCENDING), ("leaseExpiresAt", ASCENDING)], {"name": "lease"}),
    ],
    "run_events": [
        ([("runId", ASCENDING), ("seq", ASCENDING)], {"name": "run_seq", "unique": True}),
    ],
    "incidents": [
        ([("tenantId", ASCENDING), ("_id", ASCENDING)], {"name": "tenant_id"}),
        ([("repositoryId", ASCENDING), ("createdAt", ASCENDING)], {"name": "repo_created"}),
    ],
    "policies": [],
}
