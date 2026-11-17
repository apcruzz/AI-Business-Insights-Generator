# Gemini model options

The existing Business assistant dropdown offers **Gemini 3.5 Flash-Lite · Google
(cloud)** and **Gemini 3.8 Flash · Google (cloud)**. Both use the server-side
`GEMINI_API_KEY`. Select Gemini after loading data to generate an automatic
overview in the existing assistant conversation. Press **Ask** for follow-ups.
Dashboard markup, styling, navigation and charts remain unchanged.

See [Gemini setup](gemini-setup.md) for the hidden-key startup command. Restart
the Python backend after changing its environment. Temporary uploaded data and
conversations may need to be loaded again after a restart.

Both Gemini choices use the same calculation engine, structured responses,
numeric checks, evidence display and scoped conversations. The free/cloud
provider's availability, project quota and model access still determine whether
a live request succeeds. There is no automatic provider or model fallback.

The automatic overview uses the existing backend review API and appears as an
assistant message. Follow-up questions receive only the overview context from
the same dataset, filters, provider, model and account session. Completed
overviews are reused; chart and page navigation do not generate extra reviews.
If a review fails, **New conversation** retries it without adding any controls.

Reviews use a compact prompt over precomputed aggregates, instead of planning
new SQL queries. Flash-Lite uses minimal thinking and Flash uses low thinking,
with a shorter output budget. Temporary timeout/network/server failures receive
one bounded retry on the selected model. See [review limits and retry behavior](gemini-setup.md#data-and-calculations).
