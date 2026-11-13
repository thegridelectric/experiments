-- Empty the dev journal tables and the hourly derivatives (dev DB only).
TRUNCATE gridworks.readings, gridworks.messages, gridworks.cached_hourly_data;
TRUNCATE gridworks.reading_channels CASCADE;
CALL refresh_continuous_aggregate('gridworks.readings_1hr', NULL, NULL);
