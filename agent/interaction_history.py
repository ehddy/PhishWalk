"""Compact formatting for previous PhishWalk interaction steps."""

from agent.graph.state import InteractionRecord


def format_interaction_history(
    history: list[InteractionRecord],
    *,
    max_records: int = 3,
) -> str:
    """Format recent interaction records without repeating full observations."""
    if max_records < 1:
        raise ValueError("max_records must be at least 1")

    if not history:
        return "No previous interactions."

    recent_history = history[-max_records:]
    lines = ["Recent interaction history:"]

    omitted_steps = len(history) - len(recent_history)
    if omitted_steps:
        lines.append(f"[Omitted {omitted_steps} earlier steps]")

    for record in recent_history:
        plan = record["action_plan"]
        lines.append("")
        lines.append(f"ActionPlan step {record['action_plan_step']}")
        action_descriptions: list[str] = []
        for action in plan.actions:
            action_data = action.model_dump(exclude_none=True)
            action_name = action_data.pop("action")
            action_data.pop("result", None)
            arguments = ", ".join(
                f"{name}={value!r}" for name, value in action_data.items()
            )
            action_descriptions.append(
                f"{action_name}({arguments})" if arguments else action_name
            )

        if plan.plan_summary is not None:
            lines.append(f"- Plan: {plan.plan_summary}")
        lines.append(f"- Actions: {', '.join(action_descriptions)}")
        lines.append(f"- Completed: {record['completed_actions']}")
        lines.append(f"- Succeeded: {'Yes' if record['succeeded'] else 'No'}")

        if record["error"] is not None:
            lines.append(f"- Error: {record['error']}")

        dialog = record.get("dialog_observation")
        if dialog is not None:
            lines.append(
                f"- Resolved browser dialog: type={dialog['type']!r}, "
                f"message={dialog['message']!r}"
            )

        observation_error = record.get("observation_error")
        if observation_error is not None:
            lines.append(f"- Observation error: {observation_error}")

        change = record.get("change_observation")
        if change is not None:
            if change["url_changed"]:
                lines.append(
                    f"- URL: {change['previous_url']} -> {change['current_url']}"
                )
            else:
                lines.append("- URL changed: No")

            added_text_count = len(change["added_text"])
            removed_text_count = len(change["removed_text"])
            added_element_count = len(change["added_elements"])
            removed_element_count = len(change["removed_elements"])
            lines.append(
                f"- Added text: {added_text_count} "
                f"item{'s' if added_text_count != 1 else ''}"
            )
            lines.append(
                f"- Removed text: {removed_text_count} "
                f"item{'s' if removed_text_count != 1 else ''}"
            )
            lines.append(
                f"- Added interactive elements: "
                f"{added_element_count} "
                f"item{'s' if added_element_count != 1 else ''}"
            )
            lines.append(
                f"- Removed interactive elements: "
                f"{removed_element_count} "
                f"item{'s' if removed_element_count != 1 else ''}"
            )

    return "\n".join(lines)
