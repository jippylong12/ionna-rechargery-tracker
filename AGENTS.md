# Operational update reporting

When asked for a tracker/database update, query the latest `runs` document and report the exact run timestamp, counts for `discovered`, `updated`, `observed_openings`, and `missing`, plus the current total/open/coming-soon/under-renovation counts.

For every updated record, list the station and each meaningful field-level before/after value. Do not stop at an aggregate update count. Group image-only changes separately, but name every affected station and distinguish them from status, price, note, address, or other operational changes. State explicitly when no non-image changes occurred.
