# Challenge 3: Desk terminal verification demo

Original live verification: **2026-11-27**. Demo replay and report consolidation: **2026-11-28**, Asia/Calcutta.

**Result: all 30 emails validated; 0 needs_review. Agreement with 15 assistant-draft labels: 99.1% (108/109 field checks). Actual human label review remains pending.**

This single report contains the Desk commands, captured terminal responses, tests, findings and conversation record. Output blocks are actual saved or newly captured terminal text; timestamps, timings and run IDs can differ when replayed. Commands use PowerShell syntax. Output was captured by launching the same desk.cmd through cmd.exe /d /c. Working directory: `C:\Users\suganeshwaran\Desktop\AI Agents`.

## 1. Preview the selected email folder

Captured on 2026-11-28. This offline preview found all 30 current compatible outcomes and made no model calls.

```powershell
.\desk.cmd structured-output data/emails --plan-only --summary-only
```

Actual terminal response:

```text
Schema template: C:\Users\suganeshwaran\Desktop\AI Agents\skills\structured-output\order_schema.py
Emails: 30 | reusable: 30 | new requests: 0
Evaluation: 15 assistant-draft labels.
Offline plan: C:\Users\suganeshwaran\Desktop\AI Agents\output\batch-plan-f87398f19bca44d7a0b82b18d4353e71.json | no model calls made
Conversation details: latency 0.45s | input 0 tokens | output 0 tokens | model global.anthropic.claude-sonnet-5-5

Exit code: 0
```

## 2. Original live extraction of all 30 emails

Captured on 2026-11-27. This is the paid provider run, rather than the later saved-result replay. The command actually executed used Desk's Python entry point:

```powershell
.\.venv\Scripts\python.exe src/desk.py structured-output "C:\Users\suganeshwaran\Desktop\AI Agents\data\emails" --output-dir "C:\Users\suganeshwaran\Desktop\AI Agents\output" --summary-only
```

Equivalent Desk launcher command:

```powershell
.\desk.cmd structured-output data/emails --output-dir output --summary-only
```

Actual terminal response:

```text
Schema template: C:\Users\suganeshwaran\Desktop\AI Agents\skills\structured-output\order_schema.py
[1/30] EM-001: validated (run)
[2/30] EM-002: validated (run)
[3/30] EM-003: validated (run)
[4/30] EM-004: validated (run)
[5/30] EM-005: validated (run)
[6/30] EM-006: validated (run)
[7/30] EM-007: validated (run)
[8/30] EM-008: validated (run)
[9/30] EM-009: validated (run)
[10/30] EM-010: validated (run)
[11/30] EM-011: validated (run)
[12/30] EM-012: validated (run)
[13/30] EM-013: validated (run)
[14/30] EM-014: validated (run)
[15/30] EM-015: validated (run)
[16/30] EM-016: validated (run)
[17/30] EM-017: validated (run)
[18/30] EM-018: validated (run)
[19/30] EM-019: validated (run)
[20/30] EM-020: validated (run)
[21/30] EM-021: validated (run)
[22/30] EM-022: validated (run)
[23/30] EM-023: validated (run)
[24/30] EM-024: validated (run)
[25/30] EM-025: validated (run)
[26/30] EM-026: validated (run)
[27/30] EM-027: validated (run)
[28/30] EM-028: validated (run)
[29/30] EM-029: validated (run)
[30/30] EM-030: validated (run)
Emails: 30 | reusable: 0 | new requests: 30
Evaluation: 15 assistant-draft labels.
Batch: complete | C:\Users\suganeshwaran\Desktop\AI Agents\output\batch-run-4307267a6cf34c0a83b1711661a7bb90-a4e859f89950477782ab245c7de0b5ef.json
Outputs: C:\Users\suganeshwaran\Desktop\AI Agents\output/results.jsonl and needs_review.jsonl (when needed)
Human label review: C:\Users\suganeshwaran\Desktop\AI Agents\evaluation\challenge3_labels_review.md
Validation: 30/30 accounted for | validated: 30 | needs_review: 0
Detailed report: C:\Users\suganeshwaran\Desktop\AI Agents\output\accuracy-report.json
Assistant draft agreement (human review pending): 99.1% (108/109 field checks; 15/15 labelled emails validated)
Conversation details: latency 7m 47.1s | input 207.2k tokens | output 51.9k tokens | model global.anthropic.claude-sonnet-5-5 | attempts 66

Exit code: 0
```

## 3. Replay the batch and show two actual JSON outputs

Captured on 2026-11-28. All 30 emails were accounted for; only the displayed sample was limited to two. Existing compatible outputs were reused, with zero new provider requests.

```powershell
.\desk.cmd structured-output data/emails --sample-size 2
```

Actual terminal response:

```text
Schema template: C:\Users\suganeshwaran\Desktop\AI Agents\skills\structured-output\order_schema.py
[1/30] EM-001: validated (reused)
[2/30] EM-002: validated (reused)
[3/30] EM-003: validated (reused)
[4/30] EM-004: validated (reused)
[5/30] EM-005: validated (reused)
[6/30] EM-006: validated (reused)
[7/30] EM-007: validated (reused)
[8/30] EM-008: validated (reused)
[9/30] EM-009: validated (reused)
[10/30] EM-010: validated (reused)
[11/30] EM-011: validated (reused)
[12/30] EM-012: validated (reused)
[13/30] EM-013: validated (reused)
[14/30] EM-014: validated (reused)
[15/30] EM-015: validated (reused)
[16/30] EM-016: validated (reused)
[17/30] EM-017: validated (reused)
[18/30] EM-018: validated (reused)
[19/30] EM-019: validated (reused)
[20/30] EM-020: validated (reused)
[21/30] EM-021: validated (reused)
[22/30] EM-022: validated (reused)
[23/30] EM-023: validated (reused)
[24/30] EM-024: validated (reused)
[25/30] EM-025: validated (reused)
[26/30] EM-026: validated (reused)
[27/30] EM-027: validated (reused)
[28/30] EM-028: validated (reused)
[29/30] EM-029: validated (reused)
[30/30] EM-030: validated (reused)
Emails: 30 | reusable: 30 | new requests: 0
Evaluation: 15 assistant-draft labels.
Batch: complete | C:\Users\suganeshwaran\Desktop\AI Agents\output\batch-run-68dd50bc268148ec9b2fa74175aa9706-f6873c74f7064465a0d064351bbf2fc4.json
Outputs: C:\Users\suganeshwaran\Desktop\AI Agents\output/results.jsonl and needs_review.jsonl (when needed)

Sample outputs: 2 of 30 processed emails
{"email_id": "EM-001", "status": "validated", "result": {"customer": "Alder Fabrication LLC", "intent": "status", "line_items": [{"sku": null, "description": "half-inch brass shutoff valves, female pipe thread (like those used on the rinse line); SKU unknown", "quantity": 12, "unit": null}], "requested_date": null, "urgency": null, "confidence": 0.75}}
{"email_id": "EM-002", "status": "validated", "result": {"customer": "Alder Packaging LLC", "intent": "other", "line_items": [{"sku": "MS-VLV-0211", "description": "Bronze Check Valve 2 in NPT", "quantity": 60, "unit": "units"}], "requested_date": null, "urgency": null, "confidence": 0.93}}
Human label review: C:\Users\suganeshwaran\Desktop\AI Agents\evaluation\challenge3_labels_review.md
Validation: 30/30 accounted for | validated: 30 | needs_review: 0
Detailed report: C:\Users\suganeshwaran\Desktop\AI Agents\output\accuracy-report.json
Assistant draft agreement (human review pending): 99.1% (108/109 field checks; 15/15 labelled emails validated)
Conversation details: latency 3.59s | input 0 tokens | output 0 tokens | model global.anthropic.claude-sonnet-5-5

Exit code: 0
```

## 4. Print the field-level evaluation with one command

Captured on 2026-11-28. This local report scored every one of the 15 labels. It made no model calls.

```powershell
.\desk.cmd accuracy --output-dir output --field-level
```

Actual terminal response:

```text
Selected outputs: C:\Users\suganeshwaran\Desktop\AI Agents\output | config: 20875ad3dcd18fecc0aeb75fe6c5f3adf82726167d17e570270cea20a64fc113

assistant_draft_agreement | validated coverage: 15/15 | missing: 0 | review: 0
Evaluation sample: 15 of 15 labelled emails (all labels scored)
email | status | incorrect fields
EM-002 | validated | none
EM-004 | validated | none
EM-006 | validated | none
EM-008 | validated | line_items.quantity
EM-010 | validated | none
EM-012 | validated | none
EM-014 | validated | none
EM-016 | validated | none
EM-017 | validated | none
EM-019 | validated | none
EM-021 | validated | none
EM-023 | validated | none
EM-025 | validated | none
EM-027 | validated | none
EM-030 | validated | none

field | correct / total | score
customer | 15 / 15 | 100.0%
intent | 15 / 15 | 100.0%
requested_date | 15 / 15 | 100.0%
urgency | 15 / 15 | 100.0%
line_items.count | 15 / 15 | 100.0%
line_items.sku | 9 / 9 | 100.0%
line_items.quantity | 8 / 9 | 88.9%
line_items.unit | 9 / 9 | 100.0%
line_items.description | 7 / 7 | 100.0%
Report: C:\Users\suganeshwaran\Desktop\AI Agents\output\accuracy-report.json
Assistant draft labels await human review; this is not a human-labelled accuracy claim.
Assistant draft agreement (human review pending): 99.1% (108/109 field checks; 15/15 labelled emails validated)
Conversation details: latency 0.47s | input 0 tokens | output 0 tokens | model global.anthropic.claude-sonnet-5-5

Exit code: 0
```

The only disagreement is **EM-008, goggles quantity**. The source says "Maybe add four"; the draft expects `4`, while the accepted model output uses `null` and preserves "maybe add four" in its description. The label was not changed after seeing the prediction. A human should resolve this ambiguity. Confidence is not scored as accuracy. Requested-date and urgency expectations are null throughout this labelled subset, so those scores do not measure positive date/urgency extraction.

## 5. Check the human-review gate

Captured on 2026-11-28. Exit code 1 is the expected result while the annotations are unapproved. This verifies that the command refuses a human-labelled accuracy claim.

```powershell
.\desk.cmd accuracy --output-dir output --field-level --require-reviewed
```

Actual terminal response:

```text
desk: Labels are assistant drafts; a human must review/approve them before an accuracy claim.
Conversation details: latency 0.19s | input 0 tokens | output 0 tokens | model global.anthropic.claude-sonnet-5-5

Exit code: 1
```

The [structured-output skill](skills/structured-output/SKILL.md) says: "Do not mark labels approved on the user's behalf." The [15-label file](evaluation/challenge3_labels.draft.json) remains pending. A person must check/correct the labels and record their actual reviewer, date and approved status before the gated command can succeed.

## 6. Schema, native output and repair verification

| Requirement | Verified behavior |
| --- | --- |
| Schema | Canonical Pydantic schema in `skills/structured-output/order_schema.py`; `src/schemas.py` imports it. Exactly customer, intent, line_items, requested_date, urgency, confidence. |
| Line items | SKU or description required; positive finite quantity or null; unit or null. Order IDs cannot stand in for SKUs. |
| Native provider mode | Bedrock Converse sends `outputConfig.textFormat.type=json_schema`; no prompt-only fallback. |
| Validation | Every extraction is parsed with Pydantic. Unsupported types, extra fields, impossible dates and invalid bounds are rejected. |
| Repair limit | Initial response plus at most two repairs; feedback includes validation errors and the preceding response with the same email. |
| Source verification | Native-schema verifier checks a source-only evidence ledger; semantic repairs share the two-repair limit. |
| Batch accounting | 30 source-associated persisted outcomes; 30 validated and zero review outcomes. |
| Review failures | Mocked terminal tests cover invalid JSON exhaustion, refusals, verifier failure and persistence of needs_review. |
| Multi-intent | One primary intent using return > complaint > order > status > other. Quotes and stock/price enquiries map to other. |
| Alternatives | One product with mutually exclusive quantities stays one line with null quantity and the options in its description. |

The real provider receipts recorded:

```json
{
  "repair_requests": 3,
  "responses_received": 33,
  "verification_requests": 33,
  "transport_attempts": 66
}
```

EM-001, EM-002 and EM-003 each used one repair. Every other email used zero repairs. These counters include both extraction and independent source-verification requests. They are actual provider-run counters; exhaustive failure-path coverage below uses mocked provider responses.

## 7. Automated terminal tests

On 2026-11-27, after fixing a test assertion to tolerate normal terminal title wrapping, the full suite passed **82 tests**. Five were temporary verification-helper tests, removed during the requested cleanup. The retained project suite has 77 tests; its post-cleanup result is appended below. The tests use mocked Bedrock I/O and are separate evidence from the actual provider run in section 2.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s challenges/challenge3 -v
```

<details>
<summary>Actual 2026-11-27 output: all 82 test names and results</summary>

```text
test_native_request_and_transport_retry_bounds (test_challenge3_contract.ProviderTests.test_native_request_and_transport_retry_bounds) ... ok
test_unsupported_schema_is_reviewable_without_prompt_fallback (test_challenge3_contract.ProviderTests.test_unsupported_schema_is_reviewable_without_prompt_fallback) ... ok
test_exact_six_field_contract_and_primary_intent_policy (test_challenge3_contract.SchemaTests.test_exact_six_field_contract_and_primary_intent_policy) ... ok
test_missing_product_identity_and_order_number_are_rejected (test_challenge3_contract.SchemaTests.test_missing_product_identity_and_order_number_are_rejected) ... ok
test_native_schema_requires_all_fields_and_retains_local_constraints (test_challenge3_contract.SchemaTests.test_native_schema_requires_all_fields_and_retains_local_constraints) ... ok
test_numeric_types_bounds_and_unknown_keys (test_challenge3_contract.SchemaTests.test_numeric_types_bounds_and_unknown_keys) ... ok
test_legacy_label_metadata_is_ignored_by_six_field_scoring (test_challenge3_contract.ScoringTests.test_legacy_label_metadata_is_ignored_by_six_field_scoring) ... ok
test_missing_prediction_has_no_null_credit_and_confidence_is_not_scored (test_challenge3_contract.ScoringTests.test_missing_prediction_has_no_null_credit_and_confidence_is_not_scored) ... ok
test_one_prediction_cannot_cover_two_lines_and_extras_are_penalized (test_challenge3_contract.ScoringTests.test_one_prediction_cannot_cover_two_lines_and_extras_are_penalized) ... ok
test_reordered_repeated_sku_lines_keep_identical_scores (test_challenge3_contract.ScoringTests.test_reordered_repeated_sku_lines_keep_identical_scores) ... ok
test_all_thirty_inputs_have_an_outcome_including_invalid_sources (test_challenge3_contract.WorkflowTests.test_all_thirty_inputs_have_an_outcome_including_invalid_sources) ... ok
test_extra_output_fields_are_repaired_and_never_saved (test_challenge3_contract.WorkflowTests.test_extra_output_fields_are_repaired_and_never_saved) ... ok
test_extraction_refusal_is_not_retried (test_challenge3_contract.WorkflowTests.test_extraction_refusal_is_not_retried) ... ok
test_historical_rich_output_scores_only_the_explicit_core_subset (test_challenge3_contract.WorkflowTests.test_historical_rich_output_scores_only_the_explicit_core_subset) ... ok
test_invalid_json_repairs_and_exhaustion_are_persisted (test_challenge3_contract.WorkflowTests.test_invalid_json_repairs_and_exhaustion_are_persisted) ... ok
test_labels_outside_selection_and_stale_checksums_fail_before_calls (test_challenge3_contract.WorkflowTests.test_labels_outside_selection_and_stale_checksums_fail_before_calls) ... ok
test_later_review_supersedes_success_for_resume_and_accuracy (test_challenge3_contract.WorkflowTests.test_later_review_supersedes_success_for_resume_and_accuracy) ... ok
test_one_command_scores_all_fifteen_with_missing_and_review_denominators (test_challenge3_contract.WorkflowTests.test_one_command_scores_all_fifteen_with_missing_and_review_denominators) ... ok
test_source_map_permanent_denial_is_bounded_and_preserves_old_file (test_challenge3_contract.WorkflowTests.test_source_map_permanent_denial_is_bounded_and_preserves_old_file) ... ok
test_source_map_retries_temporary_windows_replace_denials (test_challenge3_contract.WorkflowTests.test_source_map_retries_temporary_windows_replace_denials) ... ok
test_storage_failure_stops_before_the_next_email_until_offline_recovery (test_challenge3_contract.WorkflowTests.test_storage_failure_stops_before_the_next_email_until_offline_recovery) ... ok
test_validation_command_and_saved_chat_end_with_accuracy (test_challenge3_contract.WorkflowTests.test_validation_command_and_saved_chat_end_with_accuracy) ... ok
test_validation_without_labels_ends_with_unmeasured_accuracy (test_challenge3_contract.WorkflowTests.test_validation_without_labels_ends_with_unmeasured_accuracy) ... ok
test_flags_complete_after_inline_skill_without_popup_in_prose (test_chat_completion.CompletionTests.test_flags_complete_after_inline_skill_without_popup_in_prose) ... ok
test_last_slash_selection_controls_current_completion (test_chat_completion.CompletionTests.test_last_slash_selection_controls_current_completion) ... ok
test_path_url_and_escaped_slashes_do_not_trigger_menu (test_chat_completion.CompletionTests.test_path_url_and_escaped_slashes_do_not_trigger_menu) ... ok
test_screenshot_prefix_filters_inline_commands (test_chat_completion.CompletionTests.test_screenshot_prefix_filters_inline_commands) ... ok
test_selection_preserves_text_before_and_after_cursor (test_chat_completion.CompletionTests.test_selection_preserves_text_before_and_after_cursor) ... ok
test_slash_at_start_or_inside_sentence_shows_same_seven_commands (test_chat_completion.CompletionTests.test_slash_at_start_or_inside_sentence_shows_same_seven_commands) ... ok
test_menu_opens_while_typing_inside_real_prompt_session (test_chat_completion.InteractiveCompletionTests.test_menu_opens_while_typing_inside_real_prompt_session) ... ok
test_invalid_unknown_or_multiple_tools_never_dispatch (test_chat_skills.ChatSkillTests.test_invalid_unknown_or_multiple_tools_never_dispatch) ... ok
test_missing_singular_folder_suggests_plural_without_running_it (test_chat_skills.ChatSkillTests.test_missing_singular_folder_suggests_plural_without_running_it) ... ok
test_misspelled_cli_option_is_reported_without_sending_it_to_model (test_chat_skills.ChatSkillTests.test_misspelled_cli_option_is_reported_without_sending_it_to_model) ... ok
test_model_selected_skill_runs_workflow_and_remembers_real_accuracy (test_chat_skills.ChatSkillTests.test_model_selected_skill_runs_workflow_and_remembers_real_accuracy) ... ok
test_normal_reply_and_clarification_do_not_execute_workflows (test_chat_skills.ChatSkillTests.test_normal_reply_and_clarification_do_not_execute_workflows) ... ok
test_paths_with_spaces_and_flags_use_argv_not_a_shell (test_chat_skills.ChatSkillTests.test_paths_with_spaces_and_flags_use_argv_not_a_shell) ... ok
test_selected_skill_with_natural_arguments_is_forwarded_to_llm (test_chat_skills.ChatSkillTests.test_selected_skill_with_natural_arguments_is_forwarded_to_llm) ... ok
test_selected_skill_with_valid_options_remains_a_local_shortcut (test_chat_skills.ChatSkillTests.test_selected_skill_with_valid_options_remains_a_local_shortcut) ... ok
test_workflow_failure_is_remembered_as_an_error_not_completion (test_chat_skills.ChatSkillTests.test_workflow_failure_is_remembered_as_an_error_not_completion) ... ok
test_fragmented_arguments_are_collected_without_printing_them (test_chat_skills.StreamTests.test_fragmented_arguments_are_collected_without_printing_them) ... ok
test_incomplete_malformed_and_non_object_tool_inputs_never_escape (test_chat_skills.StreamTests.test_incomplete_malformed_and_non_object_tool_inputs_never_escape) ... ok
test_stream_failure_does_not_publish_or_duplicate_a_partial_tool (test_chat_skills.StreamTests.test_stream_failure_does_not_publish_or_duplicate_a_partial_tool) ... ok
test_missing_labels_do_not_turn_validation_into_accuracy (test_presentation.RenderTests.test_missing_labels_do_not_turn_validation_into_accuracy) ... ok
test_narrow_email_cards_wrap_and_show_only_the_six_fields (test_presentation.RenderTests.test_narrow_email_cards_wrap_and_show_only_the_six_fields) ... ok
test_overall_score_uses_all_labelled_checks_separate_from_batch_count (test_presentation.RenderTests.test_overall_score_uses_all_labelled_checks_separate_from_batch_count) ... ok
test_plain_validation_report_is_overall_only (test_presentation.RenderTests.test_plain_validation_report_is_overall_only) ... ok
test_review_card_never_displays_an_unaccepted_prediction (test_presentation.RenderTests.test_review_card_never_displays_an_unaccepted_prediction) ... ok
test_stream_callback_preserves_reply_without_raw_duplicate_prints (test_presentation.RenderTests.test_stream_callback_preserves_reply_without_raw_duplicate_prints) ... ok
test_ask_dispatch_accepts_flags_anywhere_and_reports_usage_once (test_presentation.UsageTests.test_ask_dispatch_accepts_flags_anywhere_and_reports_usage_once) ... ok
test_chat_ask_override_preserves_default_history_and_counts_usage_once (test_presentation.UsageTests.test_chat_ask_override_preserves_default_history_and_counts_usage_once) ... ok
test_failed_gateway_request_reports_missing_usage_without_inventing_cost (test_presentation.UsageTests.test_failed_gateway_request_reports_missing_usage_without_inventing_cost) ... ok
test_future_command_gets_conversation_details_without_adding_its_own_reporting (test_presentation.UsageTests.test_future_command_gets_conversation_details_without_adding_its_own_reporting) ... ok
test_malformed_tool_keeps_reported_usage_even_when_execution_is_rejected (test_presentation.UsageTests.test_malformed_tool_keeps_reported_usage_even_when_execution_is_rejected) ... ok
test_skill_usage_includes_extraction_verification_and_session_without_rebilling_reuse (test_presentation.UsageTests.test_skill_usage_includes_extraction_verification_and_session_without_rebilling_reuse) ... ok
test_structured_output_override_reports_selected_model_without_changing_default (test_presentation.UsageTests.test_structured_output_override_reports_selected_model_without_changing_default) ... ok
test_universal_turn_counts_gateway_calls_once_and_keeps_session_totals (test_presentation.UsageTests.test_universal_turn_counts_gateway_calls_once_and_keeps_session_totals) ... ok
test_arbitrary_forty_inputs_reuse_and_fifteen_sample (test_structured_output.OfflineTests.test_arbitrary_forty_inputs_reuse_and_fifteen_sample) ... ok
test_complete_ledger_and_literal_evidence_are_enforced_locally (test_structured_output.OfflineTests.test_complete_ledger_and_literal_evidence_are_enforced_locally) ... ok
test_current_corpus_old_outputs_remain_readable_but_not_current (test_structured_output.OfflineTests.test_current_corpus_old_outputs_remain_readable_but_not_current) ... ok
test_faithful_paraphrase_does_not_require_verbatim_description (test_structured_output.OfflineTests.test_faithful_paraphrase_does_not_require_verbatim_description) ... ok
test_intent_unit_and_date_findings_use_shared_two_repair_budget (test_structured_output.OfflineTests.test_intent_unit_and_date_findings_use_shared_two_repair_budget) ... ok
test_missing_receipt_and_tampered_payload_are_rejected (test_structured_output.OfflineTests.test_missing_receipt_and_tampered_payload_are_rejected) ... ok
test_native_verifier_schema_and_no_network_fallback (test_structured_output.OfflineTests.test_native_verifier_schema_and_no_network_fallback) ... ok
test_old_contract_and_changed_verifier_are_not_reused (test_structured_output.OfflineTests.test_old_contract_and_changed_verifier_are_not_reused) ... ok
test_omitted_allowed_source_fact_is_actionable (test_structured_output.OfflineTests.test_omitted_allowed_source_fact_is_actionable) ... ok
test_schema_repair_and_semantic_repair_share_budget (test_structured_output.OfflineTests.test_schema_repair_and_semantic_repair_share_budget) ... ok
test_semantic_feedback_repairs_unsupported_prose_without_new_context (test_structured_output.OfflineTests.test_semantic_feedback_repairs_unsupported_prose_without_new_context) ... ok
test_seven_chat_commands_and_new_cli_selection (test_structured_output.OfflineTests.test_seven_chat_commands_and_new_cli_selection) ... ok
test_uncertain_and_alternative_quantities_remain_null (test_structured_output.OfflineTests.test_uncertain_and_alternative_quantities_remain_null) ... ok
test_uncertain_verdict_never_becomes_success (test_structured_output.OfflineTests.test_uncertain_verdict_never_becomes_success) ... ok
test_verified_success_has_receipt_and_isolated_context (test_structured_output.OfflineTests.test_verified_success_has_receipt_and_isolated_context) ... ok
test_verifier_provider_and_local_errors_fail_closed (test_structured_output.OfflineTests.test_verifier_provider_and_local_errors_fail_closed) ... ok
test_verifier_refusal_truncation_and_malformed_report_fail_closed (test_structured_output.OfflineTests.test_verifier_refusal_truncation_and_malformed_report_fail_closed) ... ok
test_ambiguous_config_and_latest_timestamp_fail_clearly (test_structured_output.SelectionTests.test_ambiguous_config_and_latest_timestamp_fail_clearly) ... ok
test_historical_and_model_mismatch_require_explicit_selection (test_structured_output.SelectionTests.test_historical_and_model_mismatch_require_explicit_selection) ... ok
test_human_review_is_not_automatically_approved (test_structured_output.SelectionTests.test_human_review_is_not_automatically_approved) ... ok
test_latest_and_explicit_current_output_selection (test_structured_output.SelectionTests.test_latest_and_explicit_current_output_selection) ... ok
test_a_different_email_cannot_be_substituted_by_row_order (test_validation_runner.AuditTests.test_a_different_email_cannot_be_substituted_by_row_order) ... ok
test_changed_source_cannot_pass_persisted_audit (test_validation_runner.AuditTests.test_changed_source_cannot_pass_persisted_audit) ... ok
test_different_planned_source_set_cannot_pass_audit (test_validation_runner.AuditTests.test_different_planned_source_set_cannot_pass_audit) ... ok
test_validated_and_review_outcomes_are_accounted_for (test_validation_runner.AuditTests.test_validated_and_review_outcomes_are_accounted_for) ... ok
test_explicit_field_table_is_printed_in_the_interactive_terminal (test_validation_runner.FieldTableTests.test_explicit_field_table_is_printed_in_the_interactive_terminal) ... ok

----------------------------------------------------------------------
Ran 82 tests in 35.504s

OK

Exit code: 0
```

</details>

The tests cover schema constraints, native request configuration, transport retry bounds, validation feedback, two-repair exhaustion, needs_review, source checks, one-email context isolation, all-input batching, resume behavior, missing-prediction denominators, one-to-one line matching and the seven-command chat menu.

## 8. Output integrity and evaluation preparation

The final 2026-11-27 audit revalidated all persisted payloads, checked their source IDs/checksums and current extraction fingerprints, and confirmed exact equality with the planned source set. Its result was:

```json
{
  "source_count": 30,
  "validated": 30,
  "needs_review": 0,
  "accounted_for": 30
}
```

That final replay reused 30 saved outcomes, sent zero new email payloads and reported zero input/output tokens. The 2026-11-28 demo also preserved the exact results.jsonl content.

Before the live run, the 15 draft labels were independently reread against their own source emails. Five source changes required these corrections:

| Email | Previous SKU | Current source SKU | Other correction |
| --- | --- | --- | --- |
| EM-002 | MS-VLV0211 | MS-VLV-0211 | Source checksum refreshed |
| EM-006 | MS-FST0215 | MS-FST-0215 | Source checksum refreshed |
| EM-017 | MS-VLV0200 | MS-VLV-0200 | Source checksum refreshed |
| EM-025 | MS-VLV0206 | MS-VLV-0206 | Source checksum refreshed |
| EM-030 | MS-PTL0219 | MS-PTL-0219 | Unit: selling unit -> unit |

Installed versions verified during the live run: boto3 1.44.7, botocore 1.44.7, pydantic 2.12.5, prompt-toolkit 3.0.52, rich 14.1.0.

## 9. Conversation record

User's original task:

> BUILD
> Define an OrderRequest schema (Pydantic or JSON Schema): customer, intent
> (order | status | complaint | return | other), line items (sku or description,
> quantity, unit), requested date, urgency, confidence.
> Use your provider's structured-output / JSON-schema mode.
> Validate every response. On failure, re-prompt with the validation error
> (max 2 repair attempts), then send the email to a needs_review pile.
> Batch over all 30 emails and write results.jsonl.
> Hand-label 15 emails and print field-level accuracy.
> DONE WHEN
> 100% of outputs parse and validate, or land in needs_review.
> The accuracy report runs with one command.
> Multi-intent emails are handled in a way your schema explicitly defines.
> STRETCH
> Compare a small cheap model with a large one on accuracy and cost per email.
> // test every steps in terminal and store the conversation in the challenge.md file

Subsequent user instructions and actions:

- Optional small/large-model comparison: **"leave that for now"**. It was deferred.
- **"pause all"**. Work stopped after the provider run and final checks; the report update was still unfinished.
- On 2026-11-28, the user requested a demo report with Desk commands and actual terminal responses.
- The user then requested removal of testing-created files/folders and a single report. This file consolidates that evidence.

Assistant work: preserved the existing application flow, refreshed stale source labels, ran the real provider batch, added the optional `accuracy --field-level` terminal table, checked source/output integrity and tested the failure paths. No human label approval was recorded.

## 10. Single-report cleanup

The transcript and relevant verification evidence have been embedded in this document. Cleanup removes the four generated evidence folders under documents, the two temporary verification helper files and their own bytecode, generated batch plans/manifests, and the generated accuracy-report.json. Desk may create new runtime plans or JSON reports on future invocations. Application code, source emails, the canonical schema, labels, results.jsonl and its required source/configuration/verification records are retained. The cleanup result and retained-suite check follow below.

Cleanup completed on 2026-11-28. Removed these generated artifacts after consolidating their relevant evidence:

- `documents\challenge3-final-validation-2026-11-27`
- `documents\challenge3-final-validation-2026-11-27-r2`
- `documents\challenge3-label-review-2026-11-27`
- `documents\challenge3-terminal-evidence-2026-11-27`
- `challenges\challenge3\validate.py`
- `challenges\challenge3\test_validation_runner.py`
- `challenges\challenge3\__pycache__\validate.cpython-313.pyc`
- `challenges\challenge3\__pycache__\test_validation_runner.cpython-313.pyc`
- `output\accuracy-report.json`
- `output\batch-plan-040b5e6baa5f499285d11f498a0901d8.json`
- `output\batch-plan-4307267a6cf34c0a83b1711661a7bb90.json`
- `output\batch-plan-5ce29a8937b04570966cd2d7071b3708.json`
- `output\batch-plan-68dd50bc268148ec9b2fa74175aa9706.json`
- `output\batch-plan-7f3a9896486344ab8b4a6bfe41fbc124.json`
- `output\batch-plan-f87398f19bca44d7a0b82b18d4353e71.json`
- `output\batch-run-040b5e6baa5f499285d11f498a0901d8-42a315d21310492f84c541daabddf989.json`
- `output\batch-run-4307267a6cf34c0a83b1711661a7bb90-a4e859f89950477782ab245c7de0b5ef.json`
- `output\batch-run-68dd50bc268148ec9b2fa74175aa9706-f6873c74f7064465a0d064351bbf2fc4.json`


### Post-cleanup verification of the retained test suite

Executed on 2026-11-28 after removing the five temporary helper tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s challenges/challenge3 -v
```

<details>
<summary>Actual post-cleanup terminal response</summary>

```text
test_native_request_and_transport_retry_bounds (test_challenge3_contract.ProviderTests.test_native_request_and_transport_retry_bounds) ... ok
test_unsupported_schema_is_reviewable_without_prompt_fallback (test_challenge3_contract.ProviderTests.test_unsupported_schema_is_reviewable_without_prompt_fallback) ... ok
test_exact_six_field_contract_and_primary_intent_policy (test_challenge3_contract.SchemaTests.test_exact_six_field_contract_and_primary_intent_policy) ... ok
test_missing_product_identity_and_order_number_are_rejected (test_challenge3_contract.SchemaTests.test_missing_product_identity_and_order_number_are_rejected) ... ok
test_native_schema_requires_all_fields_and_retains_local_constraints (test_challenge3_contract.SchemaTests.test_native_schema_requires_all_fields_and_retains_local_constraints) ... ok
test_numeric_types_bounds_and_unknown_keys (test_challenge3_contract.SchemaTests.test_numeric_types_bounds_and_unknown_keys) ... ok
test_legacy_label_metadata_is_ignored_by_six_field_scoring (test_challenge3_contract.ScoringTests.test_legacy_label_metadata_is_ignored_by_six_field_scoring) ... ok
test_missing_prediction_has_no_null_credit_and_confidence_is_not_scored (test_challenge3_contract.ScoringTests.test_missing_prediction_has_no_null_credit_and_confidence_is_not_scored) ... ok
test_one_prediction_cannot_cover_two_lines_and_extras_are_penalized (test_challenge3_contract.ScoringTests.test_one_prediction_cannot_cover_two_lines_and_extras_are_penalized) ... ok
test_reordered_repeated_sku_lines_keep_identical_scores (test_challenge3_contract.ScoringTests.test_reordered_repeated_sku_lines_keep_identical_scores) ... ok
test_all_thirty_inputs_have_an_outcome_including_invalid_sources (test_challenge3_contract.WorkflowTests.test_all_thirty_inputs_have_an_outcome_including_invalid_sources) ... ok
test_extra_output_fields_are_repaired_and_never_saved (test_challenge3_contract.WorkflowTests.test_extra_output_fields_are_repaired_and_never_saved) ... ok
test_extraction_refusal_is_not_retried (test_challenge3_contract.WorkflowTests.test_extraction_refusal_is_not_retried) ... ok
test_historical_rich_output_scores_only_the_explicit_core_subset (test_challenge3_contract.WorkflowTests.test_historical_rich_output_scores_only_the_explicit_core_subset) ... ok
test_invalid_json_repairs_and_exhaustion_are_persisted (test_challenge3_contract.WorkflowTests.test_invalid_json_repairs_and_exhaustion_are_persisted) ... ok
test_labels_outside_selection_and_stale_checksums_fail_before_calls (test_challenge3_contract.WorkflowTests.test_labels_outside_selection_and_stale_checksums_fail_before_calls) ... ok
test_later_review_supersedes_success_for_resume_and_accuracy (test_challenge3_contract.WorkflowTests.test_later_review_supersedes_success_for_resume_and_accuracy) ... ok
test_one_command_scores_all_fifteen_with_missing_and_review_denominators (test_challenge3_contract.WorkflowTests.test_one_command_scores_all_fifteen_with_missing_and_review_denominators) ... ok
test_source_map_permanent_denial_is_bounded_and_preserves_old_file (test_challenge3_contract.WorkflowTests.test_source_map_permanent_denial_is_bounded_and_preserves_old_file) ... ok
test_source_map_retries_temporary_windows_replace_denials (test_challenge3_contract.WorkflowTests.test_source_map_retries_temporary_windows_replace_denials) ... ok
test_storage_failure_stops_before_the_next_email_until_offline_recovery (test_challenge3_contract.WorkflowTests.test_storage_failure_stops_before_the_next_email_until_offline_recovery) ... ok
test_validation_command_and_saved_chat_end_with_accuracy (test_challenge3_contract.WorkflowTests.test_validation_command_and_saved_chat_end_with_accuracy) ... ok
test_validation_without_labels_ends_with_unmeasured_accuracy (test_challenge3_contract.WorkflowTests.test_validation_without_labels_ends_with_unmeasured_accuracy) ... ok
test_flags_complete_after_inline_skill_without_popup_in_prose (test_chat_completion.CompletionTests.test_flags_complete_after_inline_skill_without_popup_in_prose) ... ok
test_last_slash_selection_controls_current_completion (test_chat_completion.CompletionTests.test_last_slash_selection_controls_current_completion) ... ok
test_path_url_and_escaped_slashes_do_not_trigger_menu (test_chat_completion.CompletionTests.test_path_url_and_escaped_slashes_do_not_trigger_menu) ... ok
test_screenshot_prefix_filters_inline_commands (test_chat_completion.CompletionTests.test_screenshot_prefix_filters_inline_commands) ... ok
test_selection_preserves_text_before_and_after_cursor (test_chat_completion.CompletionTests.test_selection_preserves_text_before_and_after_cursor) ... ok
test_slash_at_start_or_inside_sentence_shows_same_seven_commands (test_chat_completion.CompletionTests.test_slash_at_start_or_inside_sentence_shows_same_seven_commands) ... ok
test_menu_opens_while_typing_inside_real_prompt_session (test_chat_completion.InteractiveCompletionTests.test_menu_opens_while_typing_inside_real_prompt_session) ... ok
test_invalid_unknown_or_multiple_tools_never_dispatch (test_chat_skills.ChatSkillTests.test_invalid_unknown_or_multiple_tools_never_dispatch) ... ok
test_missing_singular_folder_suggests_plural_without_running_it (test_chat_skills.ChatSkillTests.test_missing_singular_folder_suggests_plural_without_running_it) ... ok
test_misspelled_cli_option_is_reported_without_sending_it_to_model (test_chat_skills.ChatSkillTests.test_misspelled_cli_option_is_reported_without_sending_it_to_model) ... ok
test_model_selected_skill_runs_workflow_and_remembers_real_accuracy (test_chat_skills.ChatSkillTests.test_model_selected_skill_runs_workflow_and_remembers_real_accuracy) ... ok
test_normal_reply_and_clarification_do_not_execute_workflows (test_chat_skills.ChatSkillTests.test_normal_reply_and_clarification_do_not_execute_workflows) ... ok
test_paths_with_spaces_and_flags_use_argv_not_a_shell (test_chat_skills.ChatSkillTests.test_paths_with_spaces_and_flags_use_argv_not_a_shell) ... ok
test_selected_skill_with_natural_arguments_is_forwarded_to_llm (test_chat_skills.ChatSkillTests.test_selected_skill_with_natural_arguments_is_forwarded_to_llm) ... ok
test_selected_skill_with_valid_options_remains_a_local_shortcut (test_chat_skills.ChatSkillTests.test_selected_skill_with_valid_options_remains_a_local_shortcut) ... ok
test_workflow_failure_is_remembered_as_an_error_not_completion (test_chat_skills.ChatSkillTests.test_workflow_failure_is_remembered_as_an_error_not_completion) ... ok
test_fragmented_arguments_are_collected_without_printing_them (test_chat_skills.StreamTests.test_fragmented_arguments_are_collected_without_printing_them) ... ok
test_incomplete_malformed_and_non_object_tool_inputs_never_escape (test_chat_skills.StreamTests.test_incomplete_malformed_and_non_object_tool_inputs_never_escape) ... ok
test_stream_failure_does_not_publish_or_duplicate_a_partial_tool (test_chat_skills.StreamTests.test_stream_failure_does_not_publish_or_duplicate_a_partial_tool) ... ok
test_missing_labels_do_not_turn_validation_into_accuracy (test_presentation.RenderTests.test_missing_labels_do_not_turn_validation_into_accuracy) ... ok
test_narrow_email_cards_wrap_and_show_only_the_six_fields (test_presentation.RenderTests.test_narrow_email_cards_wrap_and_show_only_the_six_fields) ... ok
test_overall_score_uses_all_labelled_checks_separate_from_batch_count (test_presentation.RenderTests.test_overall_score_uses_all_labelled_checks_separate_from_batch_count) ... ok
test_plain_validation_report_is_overall_only (test_presentation.RenderTests.test_plain_validation_report_is_overall_only) ... ok
test_review_card_never_displays_an_unaccepted_prediction (test_presentation.RenderTests.test_review_card_never_displays_an_unaccepted_prediction) ... ok
test_stream_callback_preserves_reply_without_raw_duplicate_prints (test_presentation.RenderTests.test_stream_callback_preserves_reply_without_raw_duplicate_prints) ... ok
test_ask_dispatch_accepts_flags_anywhere_and_reports_usage_once (test_presentation.UsageTests.test_ask_dispatch_accepts_flags_anywhere_and_reports_usage_once) ... ok
test_chat_ask_override_preserves_default_history_and_counts_usage_once (test_presentation.UsageTests.test_chat_ask_override_preserves_default_history_and_counts_usage_once) ... ok
test_failed_gateway_request_reports_missing_usage_without_inventing_cost (test_presentation.UsageTests.test_failed_gateway_request_reports_missing_usage_without_inventing_cost) ... ok
test_future_command_gets_conversation_details_without_adding_its_own_reporting (test_presentation.UsageTests.test_future_command_gets_conversation_details_without_adding_its_own_reporting) ... ok
test_malformed_tool_keeps_reported_usage_even_when_execution_is_rejected (test_presentation.UsageTests.test_malformed_tool_keeps_reported_usage_even_when_execution_is_rejected) ... ok
test_skill_usage_includes_extraction_verification_and_session_without_rebilling_reuse (test_presentation.UsageTests.test_skill_usage_includes_extraction_verification_and_session_without_rebilling_reuse) ... ok
test_structured_output_override_reports_selected_model_without_changing_default (test_presentation.UsageTests.test_structured_output_override_reports_selected_model_without_changing_default) ... ok
test_universal_turn_counts_gateway_calls_once_and_keeps_session_totals (test_presentation.UsageTests.test_universal_turn_counts_gateway_calls_once_and_keeps_session_totals) ... ok
test_arbitrary_forty_inputs_reuse_and_fifteen_sample (test_structured_output.OfflineTests.test_arbitrary_forty_inputs_reuse_and_fifteen_sample) ... ok
test_complete_ledger_and_literal_evidence_are_enforced_locally (test_structured_output.OfflineTests.test_complete_ledger_and_literal_evidence_are_enforced_locally) ... ok
test_current_corpus_old_outputs_remain_readable_but_not_current (test_structured_output.OfflineTests.test_current_corpus_old_outputs_remain_readable_but_not_current) ... ok
test_faithful_paraphrase_does_not_require_verbatim_description (test_structured_output.OfflineTests.test_faithful_paraphrase_does_not_require_verbatim_description) ... ok
test_intent_unit_and_date_findings_use_shared_two_repair_budget (test_structured_output.OfflineTests.test_intent_unit_and_date_findings_use_shared_two_repair_budget) ... ok
test_missing_receipt_and_tampered_payload_are_rejected (test_structured_output.OfflineTests.test_missing_receipt_and_tampered_payload_are_rejected) ... ok
test_native_verifier_schema_and_no_network_fallback (test_structured_output.OfflineTests.test_native_verifier_schema_and_no_network_fallback) ... ok
test_old_contract_and_changed_verifier_are_not_reused (test_structured_output.OfflineTests.test_old_contract_and_changed_verifier_are_not_reused) ... ok
test_omitted_allowed_source_fact_is_actionable (test_structured_output.OfflineTests.test_omitted_allowed_source_fact_is_actionable) ... ok
test_schema_repair_and_semantic_repair_share_budget (test_structured_output.OfflineTests.test_schema_repair_and_semantic_repair_share_budget) ... ok
test_semantic_feedback_repairs_unsupported_prose_without_new_context (test_structured_output.OfflineTests.test_semantic_feedback_repairs_unsupported_prose_without_new_context) ... ok
test_seven_chat_commands_and_new_cli_selection (test_structured_output.OfflineTests.test_seven_chat_commands_and_new_cli_selection) ... ok
test_uncertain_and_alternative_quantities_remain_null (test_structured_output.OfflineTests.test_uncertain_and_alternative_quantities_remain_null) ... ok
test_uncertain_verdict_never_becomes_success (test_structured_output.OfflineTests.test_uncertain_verdict_never_becomes_success) ... ok
test_verified_success_has_receipt_and_isolated_context (test_structured_output.OfflineTests.test_verified_success_has_receipt_and_isolated_context) ... ok
test_verifier_provider_and_local_errors_fail_closed (test_structured_output.OfflineTests.test_verifier_provider_and_local_errors_fail_closed) ... ok
test_verifier_refusal_truncation_and_malformed_report_fail_closed (test_structured_output.OfflineTests.test_verifier_refusal_truncation_and_malformed_report_fail_closed) ... ok
test_ambiguous_config_and_latest_timestamp_fail_clearly (test_structured_output.SelectionTests.test_ambiguous_config_and_latest_timestamp_fail_clearly) ... ok
test_historical_and_model_mismatch_require_explicit_selection (test_structured_output.SelectionTests.test_historical_and_model_mismatch_require_explicit_selection) ... ok
test_human_review_is_not_automatically_approved (test_structured_output.SelectionTests.test_human_review_is_not_automatically_approved) ... ok
test_latest_and_explicit_current_output_selection (test_structured_output.SelectionTests.test_latest_and_explicit_current_output_selection) ... ok

----------------------------------------------------------------------
Ran 77 tests in 20.374s

OK

Exit code: 0
```

</details>

Final check: 77 retained tests passed, 30 results.jsonl records remain, and all report links resolve. The four generated evidence folders and two temporary helper files are absent. challenge.md is the single retained verification report.
