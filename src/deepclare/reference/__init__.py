"""M3 Reference Data Build + M4 Reference Data Service.

The build (acquisition, tree resolution, publishing) must not know about the pipeline,
the declaration, the filing contract, tenancy, or the service edge. The service
(queries) must not know who is asking, why, or what a declaration is — it never
abstains, never flags for review, never applies a domain tie-break, and never knows a
tenant.
"""
