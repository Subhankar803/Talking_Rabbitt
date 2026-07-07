"""
chat_engine.py

Conversational AI orchestration. The LLM is given the analytics_engine
functions as "tools" — it decides which to call based on the user's
question, we execute them against the real dataframe, and feed the
results back so the LLM's final answer is grounded in actual numbers
instead of guessed. This is the core "talking dashboard" mechanism.
"""
from __future__ import annotations

import json
# pyrefly: ignore [missing-import]
import anthropic
# pyrefly: ignore [missing-import]
from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types

from config import settings
from services import analytics_engine as ae
from services import forecast_engine as fe
from services import visualization_engine as ve
from services import pandas_processor as pp
from utils.logger import get_logger

logger = get_logger(__name__)

# Determine LLM provider based on settings
use_gemini = False
use_openrouter = False
if settings.LLM_MODEL and settings.LLM_MODEL.lower().startswith("gemini"):
    use_gemini = True
elif settings.ANTHROPIC_API_KEY and (
    settings.ANTHROPIC_API_KEY.startswith("AQ.") or settings.ANTHROPIC_API_KEY.startswith("AIzaSy")
):
    use_gemini = True
elif settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY.startswith("sk-or-"):
    use_openrouter = True

# Initialize client(s)
_anthropic_client = None
_gemini_client = None

if settings.ANTHROPIC_API_KEY:
    if use_gemini:
        _gemini_client = genai.Client(api_key=settings.ANTHROPIC_API_KEY)
    elif not use_openrouter:
        _anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

TOOLS = [
    {
        "name": "get_trend",
        "description": "Get the trend of a numeric metric over time (monthly), including percent change in the latest period.",
        "input_schema": {
            "type": "object",
            "properties": {"metric": {"type": "string", "description": "Column name or business term, e.g. 'sales', 'revenue'"}},
            "required": ["metric"],
        },
    },
    {
        "name": "detect_anomalies",
        "description": "Detect unusually high or low values (outliers) in a numeric metric.",
        "input_schema": {
            "type": "object",
            "properties": {"metric": {"type": "string"}},
            "required": ["metric"],
        },
    },
    {
        "name": "compare_dimension",
        "description": "Compare a metric across a categorical dimension (e.g. region, product, campaign) and rank the results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "description": "e.g. 'region', 'product', 'campaign'"},
                "metric": {"type": "string"},
            },
            "required": ["dimension", "metric"],
        },
    },
    {
        "name": "top_bottom_performers",
        "description": "Get the top N and bottom N performers of a dimension ranked by a metric.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string"},
                "metric": {"type": "string"},
                "n": {"type": "integer", "default": 5},
            },
            "required": ["dimension", "metric"],
        },
    },
    {
        "name": "forecast_metric",
        "description": "Forecast future values of a metric for the next N periods using linear regression on historical trend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "horizon_periods": {"type": "integer", "default": 6},
            },
            "required": ["metric"],
        },
    },
]

_SYSTEM_PROMPT = """You are the analytics brain inside Talking Rabbitt, an AI-powered business \
biomedical and intelligence dashboard. You answer executive questions about the user's uploaded dataset by \
calling the provided tools to fetch real numbers — never invent figures.

Rules:
- Always call at least one tool before answering a data question.
- If a tool returns an "error" field, explain the limitation plainly instead of guessing.
- Give a detailed, comprehensive, and thoroughly explained ("big") answer that addresses all aspects of the user's question, including clear descriptions of what the tools returned. Do NOT keep your answers concise.
- Use markdown formatting (headings like '###', bold text '**', bullet points, or numbered lists) to make the response highly professional, readable, and structured.
- You should ALWAYS call the most appropriate tool to fetch the necessary details. Calling a tool will automatically render a chart (trend, bar chart, scatter plot, or forecast) in the user's interface. Ensure you select the right tool so the user gets both a detailed answer and a visual chart.
- When numbers support your answer, cite them directly (percentages, totals, rankings).
"""


def _uppercase_types(d):
    if isinstance(d, dict):
        res = {}
        for k, v in d.items():
            if k == "type" and isinstance(v, str):
                res[k] = v.upper()
            else:
                res[k] = _uppercase_types(v)
        return res
    elif isinstance(d, list):
        return [_uppercase_types(item) for item in d]
    else:
        return d


def _handle_gemini_chat(df, schema: dict, message: str, dataset_summary: str) -> dict:
    if _gemini_client is None:
        return _fallback_response(df, schema, message)

    gemini_tools = []
    for tool in TOOLS:
        # Convert schema types to uppercase for Gemini
        schema_def = _uppercase_types(tool["input_schema"])
        f_decl = types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters_json_schema=schema_def
        )
        gemini_tools.append(f_decl)

    tool_config = types.Tool(function_declarations=gemini_tools)

    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"Dataset context:\n{dataset_summary}\n\nQuestion: {message}")]
        )
    ]

    tools_used = []
    chart_spec = None
    final_text = ""

    for _ in range(4):
        response = _gemini_client.models.generate_content(
            model=settings.LLM_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                tools=[tool_config],
                temperature=0.0,
            )
        )

        if response.function_calls:
            # Append model's call turn
            contents.append(response.candidates[0].content)

            response_parts = []
            for call in response.function_calls:
                tools_used.append(call.name)
                # execute function
                result = _execute_tool(df, schema, call.name, call.args)
                if chart_spec is None:
                    chart_spec = _maybe_chart(call.name, result)
                
                part = types.Part.from_function_response(
                    name=call.name,
                    response={"result": result}
                )
                response_parts.append(part)

            # Append function responses with role="tool"
            contents.append(types.Content(role="tool", parts=response_parts))
        else:
            if response.text:
                final_text = response.text
            break

    return {
        "answer": final_text or "I wasn't able to generate an answer from the available data.",
        "chart_spec": chart_spec,
        "tools_used": list(set(tools_used)),
    }


def _handle_anthropic_chat(df, schema: dict, message: str, dataset_summary: str) -> dict:
    if _anthropic_client is None:
        return _fallback_response(df, schema, message)

    tools_used = []
    messages = [{
        "role": "user",
        "content": f"Dataset context:\n{dataset_summary}\n\nQuestion: {message}",
    }]

    chart_spec = None
    final_text = ""

    for _ in range(4):  # cap tool-use loops to avoid runaway calls
        response = _anthropic_client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=1000,
            system=_SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b.text for b in response.content if b.type == "text"]
        final_text = " ".join(text_blocks) or final_text

        if not tool_calls:
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for call in tool_calls:
            tools_used.append(call.name)
            result = _execute_tool(df, schema, call.name, call.input)
            if chart_spec is None:
                chart_spec = _maybe_chart(call.name, result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(result),
            })
        messages.append({"role": "user", "content": tool_results})

        if response.stop_reason != "tool_use":
            break

    return {
        "answer": final_text or "I wasn't able to generate an answer from the available data.",
        "chart_spec": chart_spec,
        "tools_used": list(set(tools_used)),
    }


def handle_chat(df, schema: dict, message: str, dataset_summary: str) -> dict:
    if use_gemini:
        return _handle_gemini_chat(df, schema, message, dataset_summary)
    elif use_openrouter:
        return _handle_openrouter_chat(df, schema, message, dataset_summary)
    else:
        return _handle_anthropic_chat(df, schema, message, dataset_summary)


def _execute_tool(df, schema, name, args):
    try:
        if name == "get_trend":
            return ae.get_trend(df, schema, args["metric"])
        if name == "detect_anomalies":
            return ae.detect_anomalies(df, schema, args["metric"])
        if name == "compare_dimension":
            return ae.compare_dimension(df, schema, args["dimension"], args["metric"])
        if name == "top_bottom_performers":
            return ae.top_bottom_performers(df, schema, args["dimension"], args["metric"], args.get("n", 5))
        if name == "forecast_metric":
            return fe.forecast_metric(df, schema, args["metric"], args.get("horizon_periods", 6))
        return {"error": f"Unknown tool '{name}'"}
    except Exception as exc:
        logger.exception("Tool execution failed")
        return {"error": str(exc)}


def _maybe_chart(tool_name, result):
    if "error" in result:
        return None
    if tool_name == "get_trend":
        return ve.trend_to_chart(result)
    if tool_name == "compare_dimension":
        return ve.comparison_to_chart(result) if "ranking" in result else None
    if tool_name == "top_bottom_performers":
        # Create a combined comparison dict so comparison_to_chart can parse it
        combined_ranking = []
        seen_keys = set()
        dim_col = result["dimension"]
        for r in result.get("top", []):
            key = r[dim_col]
            if key not in seen_keys:
                combined_ranking.append(r)
                seen_keys.add(key)
        for r in result.get("bottom", []):
            key = r[dim_col]
            if key not in seen_keys:
                combined_ranking.append(r)
                seen_keys.add(key)
        fake_result = {
            "dimension": dim_col,
            "metric": result["metric"],
            "ranking": combined_ranking
        }
        return ve.comparison_to_chart(fake_result)
    if tool_name == "detect_anomalies":
        return ve.anomalies_to_chart(
            result["series_values"], result["series_labels"], result["anomaly_indices"]
        )
    if tool_name == "forecast_metric":
        return ve.forecast_to_chart(
            result["historical_periods"], result["historical_values"],
            result["forecast_periods"], result["forecast_values"], result["metric"],
        )
    return None


def _handle_openrouter_chat(df, schema: dict, message: str, dataset_summary: str) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        return _fallback_response(df, schema, message)

    import urllib.request
    import urllib.error
    
    # Map the tools to OpenAI tool format
    openai_tools = []
    for tool in TOOLS:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        })

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Dataset context:\n{dataset_summary}\n\nQuestion: {message}"}
    ]

    tools_used = []
    chart_spec = None
    final_text = ""

    headers = {
        "Authorization": f"Bearer {settings.ANTHROPIC_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Talking Rabbitt"
    }

    url = "https://openrouter.ai/api/v1/chat/completions"
    model = settings.LLM_MODEL
    if model == "openrouter/free" or not model:
        model = "meta-llama/llama-3-8b-instruct:free"

    for _ in range(4):  # cap tool-use loops to avoid runaway calls
        data = {
            "model": model,
            "messages": messages,
            "tools": openai_tools,
            "temperature": 0.0
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res_body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            logger.error(f"OpenRouter HTTP Error: {err_msg}")
            # Fall back to local parsing if LLM fails due to API key issues
            return _fallback_response(df, schema, message)
        except Exception as e:
            logger.error(f"OpenRouter Connection Error: {e}")
            return _fallback_response(df, schema, message)

        choices = res_body.get("choices", [])
        if not choices:
            break
        choice = choices[0]
        msg_obj = choice.get("message", {})
        
        if msg_obj.get("content"):
            final_text = msg_obj["content"]
            
        tool_calls = msg_obj.get("tool_calls", [])
        if not tool_calls:
            break
            
        # Append assistant's response with tool calls to messages
        # Remove None values and map keys appropriately
        assistant_msg = {
            "role": "assistant",
            "content": msg_obj.get("content"),
            "tool_calls": tool_calls
        }
        messages.append(assistant_msg)
        
        for call in tool_calls:
            func = call.get("function", {})
            name = func.get("name")
            call_id = call.get("id")
            
            try:
                args = json.loads(func.get("arguments", "{}"))
            except Exception:
                args = {}
                
            tools_used.append(name)
            result = _execute_tool(df, schema, name, args)
            
            if chart_spec is None:
                chart_spec = _maybe_chart(name, result)
                
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": json.dumps(result)
            })

    return {
        "answer": final_text or "I wasn't able to generate an answer from the available data.",
        "chart_spec": chart_spec,
        "tools_used": list(set(tools_used)),
    }


def _fallback_response(df, schema, message: str) -> dict:
    """A highly dynamic local analytics handler that processes the prompt using Pandas
    when no API key is set. This makes the demo fully functional and responsive locally!"""
    import re
    msg = message.lower().strip()

    # 1. Identify numeric columns and categorical columns
    numeric_cols = [col for col, dtype in schema.items() if dtype == "numeric"]
    categorical_cols = [col for col, dtype in schema.items() if dtype == "categorical"]
    
    if not numeric_cols:
        return {
            "answer": "### Quantitative Analysis Warning\n\nThis dataset does not contain any numeric columns for quantitative analysis.",
            "chart_spec": None,
            "tools_used": []
        }

    # Helper to find matching column in the text
    def find_column(cols, text):
        for col in cols:
            col_clean = col.lower().replace("_", " ").replace("-", " ")
            if col_clean in text or col.lower() in text:
                return col
        return None

    # Resolve metric and dimension
    metric = find_column(numeric_cols, msg)
    if not metric:
        metric = numeric_cols[0]

    dimension = find_column(categorical_cols, msg)
    if not dimension and categorical_cols:
        dimension = categorical_cols[0]

    # 2. Determine the query intent
    # A. Forecast
    if any(k in msg for k in ["forecast", "predict", "projection", "future", "horizon", "next"]):
        result = _execute_tool(df, schema, "forecast_metric", {"metric": metric})
        if "error" in result:
            return {"answer": f"### Forecast Analysis Error\n\nError running forecast: {result['error']}", "chart_spec": None, "tools_used": []}
        
        latest_val = result["forecast_values"][-1]
        conf = result["confidence"]
        answer = (
            f"### Forecast Analysis for '{metric}'\n\n"
            f"To project future trends, I conducted a **linear regression forecasting analysis** on the historical timeline for the **'{metric}'** metric over a 6-month horizon.\n\n"
            f"**Key Forecast Projection:**\n"
            f"- **Target Horizon Value:** By the end of the 6-month horizon, **'{metric}'** is projected to reach approximately **{latest_val:,.2f}**.\n"
            f"- **Statistical Model Confidence:** **{conf:.2f}** (higher confidence score indicates a more stable historical trendline supporting the projection).\n\n"
            f"**Analytical Context:**\n"
            f"This projection is calculated using ordinary least squares (OLS) linear regression on historical periods. It assumes that current market momentum, demand signals, and operational factors will continue along a similar linear trajectory. If there are external anomalies, seasonal variations, or sudden market shifts, actual figures may vary. The line chart below displays both the historical data series and the projected trend line, allowing you to trace the growth curve visualised across the full timeline."
        )
        chart_spec = _maybe_chart("forecast_metric", result)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["forecast_metric"]
        }

    # B. Anomalies
    elif any(k in msg for k in ["anomaly", "anomalies", "outlier", "outliers", "unusual", "spike", "spikes", "drop", "drops", "dip", "dips"]):
        result = _execute_tool(df, schema, "detect_anomalies", {"metric": metric})
        if "error" in result:
            return {"answer": f"### Anomaly Detection Error\n\nError detecting anomalies: {result['error']}", "chart_spec": None, "tools_used": []}
        
        count = result["anomalies_found"]
        if count == 0:
            answer = (
                f"### Anomaly Detection Report for '{metric}'\n\n"
                f"I performed a rigorous statistical anomaly detection sweep across all data points recorded for **'{metric}'**.\n\n"
                f"**Findings:**\n"
                f"- **No Anomalies Detected:** Every data point falls within the normal statistical threshold (specifically, within 2.5 standard deviations from the dataset mean).\n"
                f"- **Data Stability:** This suggests that **'{metric}'** shows highly consistent behavior over time with no sudden spikes or drops that would indicate data entry errors or extreme external shocks.\n\n"
                f"Please refer to the chart below to observe the flat or normal variation across the series timeline."
            )
        else:
            details = "\n".join([f"- **Row {a['row_index']}:** Value of **{a['value']:,.2f}**" for a in result["anomalies"][:5]])
            answer = (
                f"### Anomaly Detection Report for '{metric}'\n\n"
                f"I performed a statistical outlier analysis on **'{metric}'** (using a standard threshold of 2.5 standard deviations from the mean) and identified **{count} unusual data point(s)**.\n\n"
                f"**Detected Anomalies/Outliers:**\n"
                f"{details}\n\n"
                f"**Analytical Context:**\n"
                f"Anomalies of this nature often indicate critical business events, such as seasonal spikes, bulk one-off orders, operational pauses, or potential data entry errors. The scatter plot below highlights these specific anomalies visually in red against the rest of the historical distribution so you can isolate the exact periods where they occurred."
            )
        chart_spec = _maybe_chart("detect_anomalies", result)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["detect_anomalies"]
        }

    # C. Top/Bottom Performers
    elif any(k in msg for k in ["top", "best", "worst", "bottom", "highest", "lowest", "performer", "performers", "rank", "ranking", "rankings"]):
        if not dimension:
            return {"answer": "### Performance Ranking Warning\n\nTo rank performers, I need a categorical column, but none was found in this dataset.", "chart_spec": None, "tools_used": []}
        
        result = _execute_tool(df, schema, "top_bottom_performers", {"dimension": dimension, "metric": metric})
        if "error" in result:
            return {"answer": f"### Performance Ranking Error\n\nError getting performers: {result['error']}", "chart_spec": None, "tools_used": []}
        
        top_list = result["top"]
        worst_list = result["bottom"]
        top_details = "\n".join([f"- **{r[dimension]}:** **{r[metric]:,.2f}**" for r in top_list[:5]])
        worst_details = "\n".join([f"- **{r[dimension]}:** **{r[metric]:,.2f}**" for r in worst_list[:5]])
        
        answer = (
            f"### Performance Ranking of '{dimension}' by '{metric}'\n\n"
            f"I have conducted a comparative ranking analysis on the categorical dimension **'{dimension}'** based on the numeric metric **'{metric}'** to identify top performing and underperforming segments.\n\n"
            f"**Top Performing Segments:**\n"
            f"{top_details}\n\n"
            f"**Underperforming Segments:**\n"
            f"{worst_details}\n\n"
            f"**Strategic Recommendation:**\n"
            f"We recommend allocating resource optimizations, budget boosts, or promotional campaigns towards the leading segments to double down on their success. Simultaneously, a root-cause investigation should be initiated for the lower performing segments to determine if localized pricing adjustments, product mix changes, or marketing pivots are necessary. The bar chart below visualizes the performance hierarchy clearly."
        )
        chart_spec = _maybe_chart("top_bottom_performers", result)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["top_bottom_performers"]
        }

    # D. Compare/Distribution/Breakdown
    elif any(k in msg for k in ["compare", "comparison", "breakdown", "share", "proportion", "distribution", "by", "versus", "vs"]):
        if not dimension:
            return {"answer": "### Comparison Warning\n\nTo compare dimensions, I need a categorical column, but none was found in this dataset.", "chart_spec": None, "tools_used": []}
        
        result = _execute_tool(df, schema, "compare_dimension", {"dimension": dimension, "metric": metric})
        if "error" in result:
            return {"answer": f"### Comparison Error\n\nError comparing dimension: {result['error']}", "chart_spec": None, "tools_used": []}
        
        best = result["best"]
        worst = result["worst"]
        best_share = best.get('share_pct', 0)
        worst_share = worst.get('share_pct', 0)
        answer = (
            f"### Dimension Comparison & Distribution Analysis\n\n"
            f"I have analyzed the breakdown and distribution of the metric **'{metric}'** across the different segments of the **'{dimension}'** dimension.\n\n"
            f"**Key Segment Insights:**\n"
            f"- **Market Leader:** **'{best[dimension]}'** is the dominant contributor, generating a total of **{best[metric]:,.2f}** which represents **{best_share}%** of the total metric.\n"
            f"- **Lowest Contributor:** **'{worst[dimension]}'** ranks as the lowest contributor, generating **{worst[metric]:,.2f}**, representing a minor **{worst_share}%** share.\n\n"
            f"**Distribution Summary:**\n"
            f"This breakdown showcases a structural concentration. A high market share for the top segment signifies a reliance on that specific area, whereas a more balanced distribution suggests a diversified portfolio. The accompanying chart provides a clear visualization of the market share distribution across all segments."
        )
        
        # User specified or default type: check if pie is requested
        chart_type = "pie" if "pie" in msg else "bar"
        chart_spec = ve.comparison_to_chart(result, chart_type=chart_type)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["compare_dimension"]
        }

    # E. Trend (Default fallback if nothing else matched)
    else:
        result = _execute_tool(df, schema, "get_trend", {"metric": metric})
        if "error" in result:
            return {"answer": f"### Trend Analysis Error\n\nI was unable to analyze the trend: {result['error']}", "chart_spec": None, "tools_used": []}
        
        direction = result["direction"]
        change = result["latest_change_pct"]
        if change is not None:
            pct_str = f"changed by {change:+.2f}%"
            answer = (
                f"### Trend Analysis for '{metric}'\n\n"
                f"I have analyzed the historical timeline of **'{metric}'** to trace its developmental trajectory over time.\n\n"
                f"**Trend and Velocity:**\n"
                f"- **Overall Direction:** The metric has moved in a **{direction}** direction.\n"
                f"- **Recent Momentum:** In the most recent period, **'{metric}'** **{pct_str}** compared to the prior period.\n\n"
                f"**Historical Outlook:**\n"
                f"Tracking this trend line helps identify seasonal patterns or structural shifts in performance. Steady growth indicates stable momentum, while a decline suggests potential bottlenecks or market cooling. The trend graph below maps the entire series timeline to help visualize these shifts."
            )
        else:
            answer = (
                f"### Series Timeline for '{metric}'\n\n"
                f"I have compiled the full historical series data for **'{metric}'** across the available timeline.\n\n"
                f"**Observations:**\n"
                f"- **Data Distribution:** The metric has been plotted across all available consecutive periods.\n"
                f"- **Latest Status:** The historical dataset has been successfully parsed and is plotted below.\n\n"
                f"Please refer to the trend chart below to observe the chronological sequence and variation of '{metric}' across the timeline."
            )
        
        chart_spec = _maybe_chart("get_trend", result)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["get_trend"]
        }
