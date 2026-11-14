# System status report

Generated 2026-11-14 11:14 on commit `3617eef`. Regenerate with `python -m benchmark.report --agent`.

## Headline

- **Unit/integration tests:** 63/63 passed (0 failed, 0 skipped) in 137s. Full output: `pytest.txt`.
- **Deterministic benchmark (no LLM):** 26/26 passed.
- **Live-agent benchmark (Gemini free tier):** 5/5 passed.
- **Plain-language sample questions:** 10 answered; median 7.2s, 4,929 tokens each on average (free tier, cost $0). Answers: `sample_answers.md`.
- **Model fallbacks during this run:** 10 across 15 questions (free-tier models time out or are overloaded; the ladder steps down and the answer still arrives).

## Data loaded

Documents on file: 57 ok, 0 failed. OCR'd scans: 3 (Doc_2026-02-06_scan.pdf, ExxonMobil 2Q25 earnings.pdf, scan_20260730_1142.pdf).

| document type | count | without a date |
|---|---|---|
| earnings_release | 27 | 0 |
| 10-Q | 4 | 0 |
| 10-K | 7 | 0 |
| transcript | 6 | 0 |
| custodian_statement | 2 | 0 |
| broker_note | 7 | 0 |
| presentation_or_event | 4 | 0 |

| table | rows |
|---|---|
| documents | 57 |
| chunks | 768 |
| positions_books | 8 |
| trades | 88 |
| prices | 310 |
| dividends | 70 |
| corporate_actions | 1 |
| fx_rates | 34 |
| consensus_estimates | 80 |
| price_targets | 10 |
| broker_notes | 7 |
| custodian_positions | 9 |
| reconciliation | 0 |

Agent runs traced in MySQL so far: 34 (each one viewable via "Show the work").

## Deterministic benchmark

| result | area | case | detail |
|---|---|---|---|
| PASS | two custodians | COST held in both accounts is combined: 2,300 shares |  |
| PASS | two custodians | COST combined market value |  |
| PASS | books vs custodian | JPM quantity follows the custodian (7,250), not the books (7,520) |  |
| PASS | books vs custodian | Reconciliation flags JPM 7,520 vs 7,250 |  |
| PASS | books vs custodian | Reconciliation flags Trust COST missing from the books |  |
| PASS | stock split | NVDA pre-split trade 1,800 @ 779.70 becomes 18,000 @ 77.97 |  |
| PASS | stock split | NVDA post-split trade is not adjusted |  |
| PASS | CHF account | Trust UNH cost in USD from blotter (929,682) and loss (-270,244) |  |
| PASS | aggregation | Total listed securities value across both accounts |  |
| PASS | aggregation | Weights sum to 100% |  |
| PASS | aggregation | MSFT is the largest position (17.8%) |  |
| PASS | rating scales | Rating scales normalise (Overweight=Buy, Equal-weight=Hold, Underweight=Sell) |  |
| PASS | broker conflict | NVDA: Calder & Rowe PT 240 vs Westbrook 155, houses disagree |  |
| PASS | self-contradicting note | C&R NVDA note flagged: headline PT $165 vs rating box $240 |  |
| PASS | EPS basis | EPS basis differs by house (GAAP vs non-GAAP) on NVDA |  |
| PASS | considering names | LLY has three houses on file |  |
| PASS | stale/new data | UNH Halvard note postdates the 30 Jun snapshot and is flagged |  |
| PASS | dirty spreadsheet | Vendor EPS text '$4.82' (UNH Q1 2025) loaded as a number |  |
| PASS | ingestion | All PDFs ingested (57 unique), none failed |  |
| PASS | OCR | Scans read by OCR and classified (AMZN call, UNH release, XOM release) |  |
| PASS | retrieval | Exact-figure search '$50.2 billion' returns exactly the two documents that contain it (company release + Westbrook note) |  |
| PASS | no hallucination | Search for a ticker with no documents returns nothing |  |
| PASS | no hallucination | Recommendation for unknown ticker META is no_data |  |
| PASS | decision | MSFT over the 15% cap -> trim, rule position_over_cap |  |
| PASS | decision | TSLA (not held, Underweight) -> no_position_avoid |  |
| PASS | calibration | NVDA recommendation has low confidence (self-contradicting source) |  |

## Live-agent benchmark

| result | case | detail |
|---|---|---|
| PASS | Holdings in one name across accounts: How many Costco shares do I own in total? |  [43s, run 20] |
| PASS | Books vs custodian: Do my own records match the bank statements? |  [2s, run 21] |
| PASS | Unknown company: Should I buy Meta? |  [2s, run 22] |
| PASS | Broker disagreement shown: Should I sell NVIDIA? |  [3s, run 23] |
| PASS | Most bullish broker: Which broker is most bullish on Lilly, and what is their price target? |  [2s, run 24] |

## Tests

| file | test | result |
|---|---|---|
| test_agent | test_tool_call_then_answer_with_citations_and_trace | PASS |
| test_agent | test_unknown_ticker_tool_result_is_no_data | PASS |
| test_agent | test_bad_tool_args_do_not_crash | PASS |
| test_agent | test_all_models_limited_gives_friendly_message_and_trace | PASS |
| test_agent | test_step_cap | PASS |
| test_agent | test_step_cap_forces_a_toolless_final_answer | PASS |
| test_agent | test_list_documents_tool_and_date_context_in_prompt | PASS |
| test_brokers | test_normalise_rating[Calder & Rowe-Buy-positive] | PASS |
| test_brokers | test_normalise_rating[Westbrook Securities-Overweight-positive] | PASS |
| test_brokers | test_normalise_rating[Calder & Rowe-Hold-neutral] | PASS |
| test_brokers | test_normalise_rating[Westbrook Securities-Equal-weight-neutral] | PASS |
| test_brokers | test_normalise_rating[Halvard Research-Market Perform-neutral] | PASS |
| test_brokers | test_normalise_rating[Halvard Research-Underperform-negative] | PASS |
| test_brokers | test_normalise_rating[Westbrook Securities-Underweight-negative] | PASS |
| test_brokers | test_normalise_rating[Calder & Rowe-Sell-negative] | PASS |
| test_brokers | test_nvda_views_disagree_and_flag_conflict | PASS |
| test_brokers | test_lly_three_houses_and_unknown_ticker | PASS |
| test_brokers | test_unh_note_after_snapshot_flagged | PASS |
| test_documents | test_list_documents_newest_first_with_latest_flag | PASS |
| test_documents | test_list_documents_filters_and_unknown_ticker | PASS |
| test_documents | test_undated_documents_are_listed_last_and_marked | PASS |
| test_documents | test_reclassify_repairs_type_and_date_from_stored_text | PASS |
| test_documents | test_new_document_arriving_later_is_dated_findable_and_becomes_latest | PASS |
| test_ingest | test_duplicate_detected_by_content | PASS |
| test_ingest | test_classify_broker_note | PASS |
| test_ingest | test_classify_misc | PASS |
| test_ingest | test_ocr_scan_readable_and_classified | PASS |
| test_ingest | test_ingest_folder_all_files | PASS |
| test_ingest | test_watcher_ingests_new_file | PASS |
| test_ingest | test_classify_type_and_date_from_the_head[Apple_Q4_FY25_Earnings_Release.pdf-earnings_release-AAPL-2025-10-24] | PASS |
| test_ingest | test_classify_type_and_date_from_the_head[NVIDIA Q1 FY2026 Financial Results.pdf-earnings_release-NVDA-2025-05-26] | PASS |
| test_ingest | test_classify_type_and_date_from_the_head[Costco Q4 FY25 Operating Results.pdf-earnings_release-COST-2025-09-29] | PASS |
| test_ingest | test_classify_type_and_date_from_the_head[NVIDIA Announces Financial Results for First Quarter Fiscal 2027.pdf-earnings_release-NVDA-2026-05-20] | PASS |
| test_ingest | test_classify_type_and_date_from_the_head[Costco Investor Overview Oct 2025.pdf-presentation_or_event-COST-2025-09-01] | PASS |
| test_ingest | test_classify_type_and_date_from_the_head[Northgate statement 2026-06-30.pdf-custodian_statement-None-2026-06-30] | PASS |
| test_ingest | test_classify_scans_tolerates_ocr_noise | PASS |
| test_llm | test_falls_back_on_429_and_traces | PASS |
| test_llm | test_cooled_model_skipped_then_retried_after_window | PASS |
| test_llm | test_all_limited_raises_with_retry_after | PASS |
| test_llm | test_missing_model_404_cooled_long_and_other_errors_raise | PASS |
| test_llm | test_timeout_504_cools_longer_than_429 | PASS |
| test_llm | test_token_usage_is_recorded_on_the_model_step | PASS |
| test_loaders | test_spreadsheets_loaded | PASS |
| test_loaders | test_spreadsheets_idempotent | PASS |
| test_loaders | test_parse_northgate | PASS |
| test_loaders | test_parse_banque_leman | PASS |
| test_loaders | test_load_statements | PASS |
| test_portfolio | test_split_adjust_nvda | PASS |
| test_portfolio | test_cost_combined_across_entities | PASS |
| test_portfolio | test_trust_cost_in_usd_and_pnl | PASS |
| test_portfolio | test_weights_sum_to_one_and_use_custodian_qty | PASS |
| test_portfolio | test_reconcile_flags | PASS |
| test_recommend | test_over_cap_position_is_trim_with_rule_and_assumption | PASS |
| test_recommend | test_custom_policy_changes_decision | PASS |
| test_recommend | test_unh_negative_view_and_loss_reported_as_facts | PASS |
| test_recommend | test_not_held_name_gets_no_position_action | PASS |
| test_recommend | test_conflicting_sources_lower_confidence | PASS |
| test_recommend | test_unknown_ticker_has_no_data | PASS |
| test_retrieval | test_semantic_query_with_ticker_filter | PASS |
| test_retrieval | test_exact_number_found_by_bm25 | PASS |
| test_retrieval | test_unknown_ticker_returns_empty | PASS |
| test_retrieval | test_new_document_becomes_searchable | PASS |
| test_trace | test_run_steps_in_order_with_answer | PASS |
