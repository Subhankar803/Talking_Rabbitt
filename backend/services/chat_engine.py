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
use_openai = False
use_grok = False
use_groq = False

# Gather available API keys
gemini_key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY or settings.ANTHROPIC_API_KEY
anthropic_key = settings.ANTHROPIC_API_KEY
openrouter_key = settings.ANTHROPIC_API_KEY
openai_key = settings.OPENAI_API_KEY
grok_key = settings.GROK_API_KEY
groq_key = settings.GROQ_API_KEY

if settings.LLM_MODEL and settings.LLM_MODEL.lower().startswith("gemini"):
    use_gemini = True
elif settings.LLM_MODEL and (settings.LLM_MODEL.lower().startswith("gpt") or "openai" in settings.LLM_MODEL.lower()):
    use_openai = True
elif settings.LLM_MODEL and (settings.LLM_MODEL.lower().startswith("grok") or "xai" in settings.LLM_MODEL.lower()):
    use_grok = True
elif settings.LLM_MODEL and (settings.LLM_MODEL.lower().startswith("groq") or "llama" in settings.LLM_MODEL.lower() or "mixtral" in settings.LLM_MODEL.lower()):
    use_groq = True
elif gemini_key and (
    gemini_key.startswith("AQ.") or gemini_key.startswith("AIzaSy")
):
    use_gemini = True
elif openai_key and openai_key.startswith("sk-"):
    use_openai = True
elif grok_key and grok_key.startswith("xai-"):
    use_grok = True
elif groq_key and groq_key.startswith("gsk_"):
    use_groq = True
elif anthropic_key and anthropic_key.startswith("sk-or-"):
    use_openrouter = True

# Initialize client(s)
_anthropic_client = None
_gemini_client = None

if use_gemini:
    if gemini_key:
        _gemini_client = genai.Client(api_key=gemini_key)
elif use_openrouter:
    # OpenRouter calls are handled via HTTP urllib requests
    pass
else:
    if anthropic_key:
        _anthropic_client = anthropic.Anthropic(api_key=anthropic_key)

TOOLS = [
    {
        "name": "query_dataset",
        "description": "Execute a Python pandas expression or code block against the pre-loaded dataframe 'df' to query, aggregate, filter, or analyze the dataset. The code should return the final result. Pandas is already imported as 'pd'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The python pandas code to run, e.g. `df.groupby('Region')['Revenue'].sum()` or `df[df['Category']=='Toys']['Profit'].mean()`. Must be valid Python code."
                }
            },
            "required": ["code"]
        }
    }
]

_SYSTEM_PROMPT = """You are the analytics brain inside Talking Rabbitt, an AI-powered business \
biomedical and intelligence dashboard. You answer executive questions about the user's uploaded dataset by \
writing custom pandas python code and executing it using the 'query_dataset' tool to query, filter, aggregate, \
or analyze the loaded dataframe 'df'.

Formatting and Style Rules:
- You MUST give a concise, direct, point-by-point (using bullet points or numbered lists) answer that directly addresses the user's question based on the code execution results.
- Do NOT provide long introductory text, conversational filler, summaries, or any extra text. Keep it strictly focused and direct.
- Use markdown formatting (bold text '**', bullet points, or numbered lists) to structure your response.
- Do not mention the name of the tools or Python code in your final text answer unless asked. Just present the answers/results.

Dataset Query Rules:
- If the user asks for a plot or chart breakdown (e.g. comparison, trend over time, breakdown), ensure your code evaluates to/returns a pandas Series or DataFrame (e.g., via groupby, value_counts, or resampling). Returning a Series/DataFrame automatically generates a beautiful chart on the UI!
- If the user explicitly asks for a particular chart format (e.g., a pie chart, doughnut chart, or bar chart), write your query normally (evaluating to a Series or DataFrame representing the breakdown) and the system will handle formatting the output chart in the requested style.
- If the user asks strategic business questions (such as requesting promotional ideas, marketing offers, competitor advice, or suggestions on how to grow or make their market strong), you should first write a pandas query to analyze segment-level performance (e.g., grouping by categories or regions). Then, construct a detailed strategic recommendation report that refers to specific data insights from your query, proposing promotional bundles, discount codes, or targeted campaigns.
- Make sure to filter correctly by column values or datetimes as requested by the user. Look closely at the provided dataset columns in the summary.
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


def _handle_gemini_chat(df, schema: dict, message: str, dataset_summary: str, company_name: str = None) -> dict:
    if _gemini_client is None:
        return _fallback_response(df, schema, message, company_name=company_name)

    try:
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

        company_context = f"\nUser Company Name: {company_name}\n" if company_name else ""
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"Dataset context:\n{dataset_summary}{company_context}\nQuestion: {message}")]
            )
        ]

        tools_used = []
        chart_spec = None
        final_text = ""

        for _ in range(4):
            response = _gemini_client.models.generate_content(
                model=settings.LLM_MODEL.lower(),
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
    except Exception as e:
        logger.warning(f"Gemini API call failed: {e}. Falling back to local analytics.")
        return _fallback_response(df, schema, message, company_name=company_name)


def _handle_openai_chat(df, schema: dict, message: str, dataset_summary: str, company_name: str = None) -> dict:
    if not settings.OPENAI_API_KEY:
        return _fallback_response(df, schema, message, company_name=company_name)

    try:
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

        company_context = f"\nUser Company Name: {company_name}\n" if company_name else ""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Dataset context:\n{dataset_summary}{company_context}\nQuestion: {message}"}
        ]

        tools_used = []
        chart_spec = None
        final_text = ""

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        url = "https://api.openai.com/v1/chat/completions"
        model = settings.LLM_MODEL
        if not model or model == "gpt-5":
            model = "gpt-4o"

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
                logger.error(f"OpenAI HTTP Error: {err_msg}")
                return _fallback_response(df, schema, message, company_name=company_name)
            except Exception as e:
                logger.error(f"OpenAI Connection Error: {e}")
                return _fallback_response(df, schema, message, company_name=company_name)

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
    except Exception as e:
        logger.warning(f"OpenAI API call failed: {e}. Falling back to local analytics.")
        return _fallback_response(df, schema, message, company_name=company_name)


def _handle_grok_chat(df, schema: dict, message: str, dataset_summary: str, company_name: str = None) -> dict:
    if not settings.GROK_API_KEY:
        return _fallback_response(df, schema, message, company_name=company_name)

    try:
        import urllib.request
        import urllib.error
        
        # Map the tools to Grok/OpenAI tool format
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

        company_context = f"\nUser Company Name: {company_name}\n" if company_name else ""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Dataset context:\n{dataset_summary}{company_context}\nQuestion: {message}"}
        ]

        tools_used = []
        chart_spec = None
        final_text = ""

        headers = {
            "Authorization": f"Bearer {settings.GROK_API_KEY}",
            "Content-Type": "application/json",
        }

        url = "https://api.x.ai/v1/chat/completions"
        model = settings.LLM_MODEL
        if not model or model == "grok":
            model = "grok-3"  # map grok to grok-3 (since it is the active/valid model ID we confirmed)

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
                logger.error(f"Grok HTTP Error: {err_msg}")
                return _fallback_response(df, schema, message, company_name=company_name)
            except Exception as e:
                logger.error(f"Grok Connection Error: {e}")
                return _fallback_response(df, schema, message, company_name=company_name)

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
    except Exception as e:
        logger.warning(f"Grok API call failed: {e}. Falling back to local analytics.")
        return _fallback_response(df, schema, message, company_name=company_name)


def _handle_groq_chat(df, schema: dict, message: str, dataset_summary: str, company_name: str = None) -> dict:
    if not settings.GROQ_API_KEY:
        return _fallback_response(df, schema, message, company_name=company_name)

    try:
        import urllib.request
        import urllib.error
        
        # Map the tools to Groq/OpenAI tool format
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

        company_context = f"\nUser Company Name: {company_name}\n" if company_name else ""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Dataset context:\n{dataset_summary}{company_context}\nQuestion: {message}"}
        ]

        tools_used = []
        chart_spec = None
        final_text = ""

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        url = "https://api.groq.com/openai/v1/chat/completions"
        model = settings.LLM_MODEL
        if not model or model.lower() == "groq" or model.lower() == "llama3-8b-8192":
            model = "llama-3.1-8b-instant"  # map groq/llama3-8b-8192 to llama-3.1-8b-instant

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
                logger.error(f"Groq HTTP Error: {err_msg}")
                return _fallback_response(df, schema, message, company_name=company_name)
            except Exception as e:
                logger.error(f"Groq Connection Error: {e}")
                return _fallback_response(df, schema, message, company_name=company_name)

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
    except Exception as e:
        logger.warning(f"Groq API call failed: {e}. Falling back to local analytics.")
        return _fallback_response(df, schema, message, company_name=company_name)


def _handle_anthropic_chat(df, schema: dict, message: str, dataset_summary: str, company_name: str = None) -> dict:
    if _anthropic_client is None:
        return _fallback_response(df, schema, message, company_name=company_name)

    try:
        tools_used = []
        company_context = f"\nUser Company Name: {company_name}\n" if company_name else ""
        messages = [{
            "role": "user",
            "content": f"Dataset context:\n{dataset_summary}{company_context}\nQuestion: {message}",
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
    except Exception as e:
        logger.warning(f"Anthropic API call failed: {e}. Falling back to local analytics.")
        return _fallback_response(df, schema, message, company_name=company_name)


def handle_chat(df, schema: dict, message: str, dataset_summary: str, company_name: str = None) -> dict:
    if use_gemini:
        res = _handle_gemini_chat(df, schema, message, dataset_summary, company_name=company_name)
    elif use_openai:
        res = _handle_openai_chat(df, schema, message, dataset_summary, company_name=company_name)
    elif use_grok:
        res = _handle_grok_chat(df, schema, message, dataset_summary, company_name=company_name)
    elif use_groq:
        res = _handle_groq_chat(df, schema, message, dataset_summary, company_name=company_name)
    elif use_openrouter:
        res = _handle_openrouter_chat(df, schema, message, dataset_summary, company_name=company_name)
    else:
        res = _handle_anthropic_chat(df, schema, message, dataset_summary, company_name=company_name)

    # Post-process chart type if user explicitly requested a pie, doughnut, or map chart
    if res.get("chart_spec"):
        msg_lower = message.lower()
        if any(k in msg_lower for k in ["pie chart", "piechart", "pie-chart", " pie "]) or msg_lower.endswith(" pie"):
            res["chart_spec"]["type"] = "pie"
        elif any(k in msg_lower for k in ["doughnut chart", "doughnutchart", "doughnut-chart", " doughnut "]) or msg_lower.endswith(" doughnut"):
            res["chart_spec"]["type"] = "doughnut"
        elif any(k in msg_lower for k in ["map", "global chart", "world map", "map chart", "geochart"]):
            if res["chart_spec"].get("type") in ["bar", "pie", "doughnut", "line"]:
                labels = res["chart_spec"].get("labels", [])
                dataset_data = res["chart_spec"].get("datasets", [{}])[0].get("data", [])
                metric_name = res["chart_spec"].get("datasets", [{}])[0].get("label", "Value")
                
                map_data = {}
                for idx, label in enumerate(labels):
                    val = dataset_data[idx] if idx < len(dataset_data) else 0
                    codes = ve._resolve_to_iso(label)
                    for code in codes:
                        map_data[code] = val
                        
                res["chart_spec"] = {
                    "type": "map",
                    "dimension": "Region",
                    "metric": metric_name,
                    "map_data": map_data
                }

    return res


import pandas as pd
import numpy as np


def _pandas_to_chart(val) -> dict | None:
    try:
        if isinstance(val, pd.Series):
            labels = [str(x) for x in val.index]
            data = [float(x) for x in val.values]
            chart_type = "bar"
            if len(labels) > 0:
                import re
                if any(re.match(r"\b\d{4}[-/]\d{2}\b", l) for l in labels[:3]):
                    chart_type = "line"
            return {
                "type": chart_type,
                "labels": labels,
                "datasets": [{
                    "label": str(val.name or "Value"),
                    "data": data
                }]
            }
        elif isinstance(val, pd.DataFrame):
            if val.empty:
                return None
            labels = [str(x) for x in val.index]
            datasets = []
            for col in val.columns:
                if pd.api.types.is_numeric_dtype(val[col]):
                    datasets.append({
                        "label": str(col),
                        "data": [float(x) for x in val[col].values]
                    })
            if datasets:
                chart_type = "bar"
                if len(labels) > 0:
                    import re
                    if any(re.match(r"\b\d{4}[-/]\d{2}\b", l) for l in labels[:3]):
                        chart_type = "line"
                return {
                    "type": chart_type,
                    "labels": labels,
                    "datasets": datasets
                }
        return None
    except Exception:
        return None


def query_dataset(df: pd.DataFrame, schema: dict, code: str) -> dict:
    try:
        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        local_vars = {"df": df, "pd": pd, "np": np}
        
        import io
        import sys
        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output
        
        try:
            is_expression = False
            try:
                compiled = compile(code, "<string>", "eval")
                is_expression = True
            except SyntaxError:
                pass
                
            if is_expression:
                result_val = eval(code, {"__builtins__": __builtins__}, local_vars)
            else:
                exec(code, {"__builtins__": __builtins__}, local_vars)
                result_val = redirected_output.getvalue().strip()
                if not result_val:
                    if "result" in local_vars:
                        result_val = local_vars["result"]
                    elif "output" in local_vars:
                        result_val = local_vars["output"]
                    else:
                        result_val = "Executed successfully."
        finally:
            sys.stdout = old_stdout
            
        chart_spec = None
        if isinstance(result_val, (pd.Series, pd.DataFrame)):
            chart_spec = _pandas_to_chart(result_val)
            try:
                result_str = result_val.to_markdown()
            except Exception:
                result_str = result_val.to_string()
        else:
            result_str = str(result_val)
            
        return {
            "result": result_str,
            "chart_spec": chart_spec
        }
    except Exception as e:
        return {"error": str(e)}


def _execute_tool(df, schema, name, args):
    try:
        year = args.get("year")
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None

        filter_col = args.get("filter_col")
        filter_val = args.get("filter_val")

        if name == "get_trend":
            return ae.get_trend(df, schema, args["metric"], year=year, filter_col=filter_col, filter_val=filter_val)
        if name == "detect_anomalies":
            return ae.detect_anomalies(df, schema, args["metric"], year=year, filter_col=filter_col, filter_val=filter_val)
        if name == "compare_dimension":
            return ae.compare_dimension(
                df, schema, args["dimension"], args.get("metric"), year=year,
                chart_type=args.get("chart_type", "bar"), agg=args.get("agg", "sum"),
                filter_col=filter_col, filter_val=filter_val
            )
        if name == "top_bottom_performers":
            return ae.top_bottom_performers(
                df, schema, args["dimension"], args.get("metric"), args.get("n", 5), year=year,
                chart_type=args.get("chart_type", "bar"), agg=args.get("agg", "sum"),
                filter_col=filter_col, filter_val=filter_val
            )
        if name == "forecast_metric":
            return fe.forecast_metric(
                df, schema, args["metric"], args.get("horizon_periods", 6),
                filter_col=filter_col, filter_val=filter_val
            )
        if name == "get_aggregate":
            return ae.get_aggregate(
                df, schema, args["metric"], agg=args.get("agg", "sum"), year=year,
                filter_col=filter_col, filter_val=filter_val
            )
        if name == "query_dataset":
            return query_dataset(df, schema, args["code"])
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
        return ve.comparison_to_chart(result, chart_type=result.get("chart_type", "bar")) if "ranking" in result else None
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
        return ve.comparison_to_chart(fake_result, chart_type=result.get("chart_type", "bar"))
    if tool_name == "detect_anomalies":
        return ve.anomalies_to_chart(
            result["series_values"], result["series_labels"], result["anomaly_indices"]
        )
    if tool_name == "forecast_metric":
        metric_name = result["metric"]
        if result.get("filter_val"):
            metric_name = f"{metric_name} ({result['filter_val']})"
        return ve.forecast_to_chart(
            result["historical_periods"], result["historical_values"],
            result["forecast_periods"], result["forecast_values"], metric_name,
        )
    if tool_name == "get_aggregate":
        return ve.trend_to_chart(result) if result.get("periods") else None
    if tool_name == "query_dataset":
        return result.get("chart_spec")
    return None


def _handle_openrouter_chat(df, schema: dict, message: str, dataset_summary: str, company_name: str = None) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        return _fallback_response(df, schema, message, company_name=company_name)

    try:
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

        company_context = f"\nUser Company Name: {company_name}\n" if company_name else ""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Dataset context:\n{dataset_summary}{company_context}\nQuestion: {message}"}
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
                return _fallback_response(df, schema, message, company_name=company_name)
            except Exception as e:
                logger.error(f"OpenRouter Connection Error: {e}")
                return _fallback_response(df, schema, message, company_name=company_name)

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
    except Exception as e:
        logger.warning(f"OpenRouter API call failed: {e}. Falling back to local analytics.")
        return _fallback_response(df, schema, message, company_name=company_name)


def _fallback_response(df, schema, message: str, company_name: str = None) -> dict:
    """A highly dynamic local analytics handler that processes the prompt using Pandas
    when no API key is set. This makes the demo fully functional and responsive locally!"""
    import re
    msg = message.lower().strip()

    # 1. Identify numeric columns and dimension columns (categorical + text columns)
    numeric_cols = [col for col, dtype in schema.items() if dtype == "numeric"]
    dim_cols = [col for col, dtype in schema.items() if dtype in ["categorical", "text"]]
    categorical_cols = [col for col, dtype in schema.items() if dtype == "categorical"]
    
    # If there is a datetime column, add 'year' and 'month' as virtual dimensions
    date_col = next((col for col, dtype in schema.items() if dtype == "datetime"), None)
    if date_col:
        dim_cols.extend(["year", "month"])
    
    if not numeric_cols:
        return {
            "answer": "### Quantitative Analysis Warning\n\n- **No Numeric Data**: This dataset does not contain any numeric columns for quantitative analysis.",
            "chart_spec": None,
            "tools_used": []
        }

    # Resolve metric and dimension
    def find_column(cols, text):
        stop_words = {"using", "with", "show", "give", "plot", "chart", "make", "find", "list", "get", "view", "display", "metric", "column", "data", "dataset", "table", "file", "please", "me", "our", "my", "pie", "bar", "line", "scatter", "selling", "sell", "sold"}
        # First, try to find a column name that is present in the text (exact or clean)
        for col in cols:
            col_clean = col.lower().replace("_", " ").replace("-", " ")
            if col_clean in stop_words:
                continue
            if col_clean in text or col.lower() in text:
                return col
        # If not found, try to see if any word from the text matches or is part of a column name
        words = [w.strip("?,.!") for w in text.split()]
        for word in words:
            if len(word) < 3 or word.lower() in stop_words:
                continue
            for col in cols:
                col_clean = col.lower().replace("_", " ").replace("-", " ")
                if word in col_clean or word in col.lower():
                    return col
        # If not found, try fuzzy match on each word to handle typos (e.g. "coustomers" -> "customer")
        import difflib
        possibilities = {}
        for col in cols:
            possibilities[col.lower().replace("_", " ").replace("-", " ")] = col
            possibilities[col.lower()] = col
        
        for word in words:
            if len(word) < 3 or word.lower() in stop_words:
                continue
            matches = difflib.get_close_matches(word, list(possibilities.keys()), n=1, cutoff=0.5)
            if matches:
                return possibilities[matches[0]]
        return None

    metric = find_column(numeric_cols, msg)
    if not metric:
        # Try to find a sensible default business metric instead of numeric_cols[0]
        for default_m in ["revenue", "sales", "profit", "amount"]:
            match = next((col for col in numeric_cols if default_m in col.lower()), None)
            if match:
                metric = match
                break
        if not metric:
            metric = numeric_cols[0]

    dimension = None
    if "country" in msg or "countries" in msg:
        for col in dim_cols:
            if "country" in col.lower() or "region" in col.lower():
                dimension = col
                break
    if not dimension:
        dimension = find_column(dim_cols, msg)
    if not dimension and dim_cols:
        # Prefer categorical over text for default dimension fallback
        cat_cols = [col for col in dim_cols if col in schema and schema[col] == "categorical"]
        dimension = cat_cols[0] if cat_cols else dim_cols[0]

    # Extract year if present (e.g., 2024, 2025)
    year = None
    year_match = re.search(r"\b(20\d{2})\b", msg)
    if year_match:
        try:
            year = int(year_match.group(1))
        except ValueError:
            pass

    # Extract filter column and value
    filter_col = None
    filter_val = None
    for col in categorical_cols:
        try:
            unique_vals = [str(val) for val in df[col].dropna().unique()]
            for val in unique_vals:
                val_clean = val.lower().strip()
                if not val_clean:
                    continue
                # Match if value is in message, or starts with, or is part of a word in message
                if val_clean in msg or any(val_clean in w for w in msg.split()):
                    filter_col = col
                    filter_val = val
                    break
        except Exception:
            continue
        if filter_col:
            break

    # 0.0. General Summary / Dashboard / Executive Report Check
    if any(k in msg for k in ["summary", "summariz", "dashboard", "report", "kpi", "metric", "matrice", "matrix"]):
        from services import report_engine
        from services import pandas_processor as pp
        
        kpis = pp.compute_kpis(df, schema)
        report = report_engine.build_executive_report(df, schema)
        
        # Build a beautiful executive summary list of KPIs
        kpi_lines = []
        kpi_lines.append(f"- **Total Rows**: {kpis.get('row_count', len(df)):,}")
        
        for k, v in kpis.items():
            if k == "row_count":
                continue
            name = k.replace("_", " ").title()
            if "total" in k:
                kpi_lines.append(f"- **{name}**: {v:,.2f}")
            elif "avg" in k:
                kpi_lines.append(f"- **{name}**: {v:,.2f}")
            else:
                kpi_lines.append(f"- **{name}**: {v}")
                
        # Also summarize other numeric columns not captured in predefined KPIs
        captured_cols = []
        for candidates in [["revenue", "sales", "amount", "total"], ["profit", "margin"], ["order", "quantity", "units"]]:
            numeric_cols = [c for c, t in schema.items() if t == "numeric"]
            col = pp._match_column(numeric_cols, candidates)
            if col:
                captured_cols.append(col)
                
        other_numerics = [c for c, t in schema.items() if t == "numeric" and c not in captured_cols]
        for col in other_numerics:
            col_sum = float(df[col].sum())
            col_avg = float(df[col].mean())
            kpi_lines.append(f"- **Total {col}**: {col_sum:,.2f}")
            kpi_lines.append(f"- **Average {col}**: {col_avg:,.2f}")

        kpis_str = "\n".join(kpi_lines)
        
        answer = (
            f"### Executive Summary & Dashboard Metrics\n\n"
            f"Here is a summary of the key metrics in your dataset:\n\n"
            f"{kpis_str}\n\n"
            f"#### Key Business Insights\n"
            + "\n".join([f"- {insight}" for insight in report.get("key_insights", [])]) + "\n\n"
            f"#### Business Health: **{report.get('business_health', 'Stable')}**\n"
            f"- {report.get('summary', '')}"
        )
        
        return {
            "answer": answer,
            "chart_spec": None,
            "tools_used": []
        }

    # 0. Rival Company / Competition Check
    if any(k in msg for k in ["stay tuned", "survive", "competition", "competitor", "competitors", "rival", "rivals"]):
        comp_name = company_name or "our company"
        answer = (
            f"### Market Survival & Competitor Analysis for **{comp_name}**\n\n"
            f"- **Competitor Landscape**: Direct rivals include large-scale operators (**WidgetCorp**), agile tech providers (**InnovateLLC**), and low-cost manufacturers (**Acme Inc**).\n"
            f"- **Strategic Survival Recommendations**:\n"
            f"  - **Product Differentiation**: Focus on high-margin product offerings to avoid price wars.\n"
            f"  - **Marketing Channels**: Expand campaign outreach across targeted Social and Email campaigns.\n"
            f"  - **Retention**: Offer loyalty rewards and personalized services to retain key accounts."
        )
        return {
            "answer": answer,
            "chart_spec": None,
            "tools_used": []
        }

    # 2. Determine the query intent
    # F. Strategic Advisory / Offers / Business Recommendations
    if any(k in msg for k in ["suggest", "idea", "ideas", "offer", "offers", "strategy", "strategic", "improve", "strong", "growth", "grow", "market", "recommendations", "marketing"]):
        if dimension:
            result = ae.compare_dimension(df, schema, dimension, metric)
            if "error" not in result and len(result.get("ranking", [])) >= 2:
                ranking = result["ranking"]
                best_seg = ranking[0][result["dimension"]]
                best_val = ranking[0][result["metric"]]
                worst_seg = ranking[-1][result["dimension"]]
                worst_val = ranking[-1][result["metric"]]
                
                import random
                bundle_ideas = [
                    f"Pair high-performing products from **{best_seg}** with underperforming items in **{worst_seg}** to raise average basket sizes.",
                    f"Launch a cross-promotional bundle combining **{best_seg}** best-sellers and **{worst_seg}** inventory at a 10% package discount.",
                    f"Create a 'Buy One Get One' (BOGO) offer that bundles key items from **{best_seg}** with accessories from **{worst_seg}**."
                ]
                discount_ideas = [
                    f"Introduce a limited-time 15% discount code specifically for customers buying in **{worst_seg}** to stimulate segment-level transaction density.",
                    f"Offer free shipping for orders exceeding $50 in the **{worst_seg}** segment to remove checkout friction.",
                    f"Run a weekend flash sale with targeted discounts on underperforming lines in **{worst_seg}**."
                ]
                retention_ideas = [
                    f"Target past purchasers in **{worst_seg}** whose transaction counts have dropped recently with targeted email coupons.",
                    f"Send a re-engagement newsletter to customers in the **{worst_seg}** region offering loyalty points multipliers.",
                    f"Conduct customer satisfaction surveys in **{worst_seg}** to identify if service issues triggered the drop."
                ]
                general_ideas = [
                    f"Recover sales in **{worst_seg}**: Sales in this segment are currently lowest at **{worst_val:,.2f}** compared to **{best_val:,.2f}** in **{best_seg}**. Check for shipping delays or competitor pricing updates.",
                    f"Evaluate pricing & competitor pressure: Check if competitor promotions or pricing updates contributed to the segment drops.",
                    f"Cross-Selling Program: Recommend related products during checkout to increase order volumes across all regions.",
                    f"Optimize ad spend: Allocate budget from lower performing dimensions into the top-converting segments like **{best_seg}**."
                ]
                
                s1 = random.choice(bundle_ideas)
                s2 = random.choice(discount_ideas)
                s3 = random.choice(retention_ideas)
                s4 = random.choice(general_ideas)
                
                answer = (
                    f"### Strategic Growth & Market Recommendations\n\n"
                    f"Based on our segment analysis of **{metric}** across **{dimension}**, here are targeted strategies to strengthen your market position:\n\n"
                    f"#### 1. Targeted Promotions & Promotional Bundles\n"
                    f"- **Product Bundle**: {s1}\n"
                    f"- **Discount Offer**: {s2}\n\n"
                    f"#### 2. Segment-Specific Interventions\n"
                    f"- **Focus on {worst_seg}**: {s4}\n"
                    f"- **Leverage {best_seg}**: Double down on successful advertising channels in **{best_seg}** to capture and retain maximum market share.\n\n"
                    f"#### 3. Strategic Loyalty Offers\n"
                    f"- **Customer Retention**: {s3}\n"
                    f"- **Cross-Selling Program**: Recommend related products during checkout to increase average order size across all regions."
                )
                chart_spec = ve.comparison_to_chart(result, chart_type="bar")
                return {
                    "answer": answer,
                    "chart_spec": chart_spec,
                    "tools_used": ["compare_dimension"]
                }
                
        comp_name = company_name or "our company"
        answer = (
            f"### General Market Strategy for **{comp_name}**\n\n"
            f"To strengthen overall market positioning and boost **{metric}**:\n\n"
            f"1. **Customer Acquisition Offers**: Propose a new-user discount (e.g., 10% off first purchase) to drive customer sign-ups.\n"
            f"2. **Seasonal Bundling**: Package related products together to raise average order values.\n"
            f"3. **Feedback Optimization**: Gather reviews and customer input to locate buying friction and improve retention."
        )
        return {
            "answer": answer,
            "chart_spec": None,
            "tools_used": []
        }

    # A. Forecast
    if any(k in msg for k in ["forecast", "predict", "projection", "future", "horizon", "next"]):
        args = {"metric": metric}
        if filter_col and filter_val:
            args["filter_col"] = filter_col
            args["filter_val"] = filter_val
        result = _execute_tool(df, schema, "forecast_metric", args)
        if "error" in result:
            return {"answer": f"### Forecast Analysis Error\n\n- **Error**: {result['error']}", "chart_spec": None, "tools_used": []}
        
        latest_val = result["forecast_values"][-1]
        conf = result["confidence"]
        filter_text = f" for **{filter_val}** ({filter_col})" if filter_val else ""
        answer = (
            f"### Forecast Analysis for **{metric}**{filter_text}\n\n"
            f"- **Target Horizon Projection**: Projected to reach approximately **{latest_val:,.2f}** over the next 6 periods.\n"
            f"- **Model Confidence Score**: **{conf:.2f}** (OLS Linear Regression)."
        )
        chart_spec = _maybe_chart("forecast_metric", result)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["forecast_metric"]
        }

    # B. Anomalies
    elif any(k in msg for k in ["anomaly", "anomalies", "outlier", "outliers", "unusual", "spike", "spikes", "drop", "drops", "dip", "dips", "why", "decrease", "decline", "reason"]):
        # Check if the user is asking to explain a drop/reason
        if any(k in msg for k in ["why", "reason", "cause", "drop", "decrease", "decline"]):
            analysis = ae.analyze_drop_reasons(df, schema, metric)
            if "error" not in analysis:
                metric_name = analysis["metric"]
                period = analysis["period"]
                prev_period = analysis["prev_period"]
                total_drop = analysis["total_drop"]
                pct_drop = analysis["pct_drop"]
                
                drivers_text = []
                for d in analysis["drivers"][:3]:
                    drivers_text.append(
                        f"- **{d['dimension']} ({d['segment']})**: dropped by **{d['amount']:,.2f}** (a **{d['pct']:.1f}%** drop in this segment)."
                    )
                drivers_str = "\n".join(drivers_text) if drivers_text else "- No specific segment declines could be isolated."
                
                primary_dim = analysis["drivers"][0]["dimension"] if analysis["drivers"] else "key categories"
                primary_seg = analysis["drivers"][0]["segment"] if analysis["drivers"] else "low-performing areas"
                
                answer = (
                    f"### Analysis of **{metric_name}** Drop ({period} vs {prev_period})\n\n"
                    f"Our local diagnostics indicate that **{metric_name}** dropped by **{total_drop:,.2f}** (**{pct_drop:.1f}%** decrease) "
                    f"from **{analysis['prev_total']:,.2f}** in {prev_period} down to **{analysis['curr_total']:,.2f}** in {period}.\n\n"
                    f"#### Key Drivers of the Decline:\n{drivers_str}\n\n"
                    f"#### Strategic Recommendations:\n"
                    f"1. **Recover sales in {primary_seg} ({primary_dim})**: The segment witnessed the largest drop in absolute volume. Check for shipping delays, customer retention issues, or promotional expiration in this region.\n"
                    f"2. **Conduct client outreach**: Run a targeted promotion or outreach campaign to re-engage customers who reduced purchasing frequency during this period.\n"
                    f"3. **Evaluate pricing & competitor pressure**: Check if competitor promotions or pricing updates contributed to the segment drops."
                )
                
                try:
                    df_copy = df.copy()
                    df_copy[analysis["date_col"]] = pd.to_datetime(df_copy[analysis["date_col"]])
                    df_copy['period'] = df_copy[analysis["date_col"]].dt.to_period('M').astype(str)
                    monthly_sum = df_copy.groupby('period')[metric_name].sum().reset_index()
                    monthly_sum = monthly_sum.sort_values('period')
                    
                    chart_spec = {
                        "type": "line",
                        "labels": monthly_sum['period'].tolist(),
                        "datasets": [{
                            "label": metric_name,
                            "data": monthly_sum[metric_name].tolist()
                        }]
                    }
                except Exception:
                    chart_spec = None
                    
                return {
                    "answer": answer,
                    "chart_spec": chart_spec,
                    "tools_used": ["detect_anomalies"]
                }

        args = {"metric": metric, "year": year}
        if filter_col and filter_val:
            args["filter_col"] = filter_col
            args["filter_val"] = filter_val
        result = _execute_tool(df, schema, "detect_anomalies", args)
        if "error" in result:
            return {"answer": f"### Anomaly Detection Error\n\n- **Error**: {result['error']}", "chart_spec": None, "tools_used": []}
        
        count = result["anomalies_found"]
        filter_text = f" for **{filter_val}** ({filter_col})" if filter_val else ""
        year_text = f" in **{year}**" if year else ""
        if count == 0:
            answer = (
                f"### Anomaly Detection Report for **{metric}**{filter_text}{year_text}\n\n"
                f"- **No Anomalies Detected**: All data points are within standard statistical thresholds (2.5 standard deviations)."
            )
        else:
            details = "\n".join([f"  - Row {a['row_index']}: Value of **{a['value']:,.2f}**" for a in result["anomalies"][:5]])
            answer = (
                f"### Anomaly Detection Report for **{metric}**{filter_text}{year_text}\n\n"
                f"- **Anomalies Identified**: Found **{count}** statistical outlier(s):\n"
                f"{details}"
            )
        chart_spec = _maybe_chart("detect_anomalies", result)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["detect_anomalies"]
        }

    # C. Top/Bottom Performers
    elif any(k in msg for k in ["top", "best", "worst", "bottom", "highest", "lowest", "most", "least", "performer", "performers", "rank", "ranking", "rankings"]):
        if not dimension:
            return {"answer": "### Performance Ranking Warning\n\n- **Missing Dimension**: To rank performers, a categorical column is required but none was found.", "chart_spec": None, "tools_used": []}
        
        # Extract N from the message if present (e.g. "top 3", "best 5", etc.)
        n = 5
        n_match = re.search(r"\b(?:top|bottom|best|worst|first|last|highest|lowest|most|least)\s+(\d+)\b", msg)
        if n_match:
            try:
                n = int(n_match.group(1))
            except ValueError:
                pass

        args = {"dimension": dimension, "metric": metric, "year": year, "n": n}
        if filter_col and filter_val:
            args["filter_col"] = filter_col
            args["filter_val"] = filter_val
        result = _execute_tool(df, schema, "top_bottom_performers", args)
        if "error" in result:
            return {"answer": f"### Performance Ranking Error\n\n- **Error**: {result['error']}", "chart_spec": None, "tools_used": []}
        
        top_list = result["top"]
        worst_list = result["bottom"]
        top_details = "\n".join([f"  - **{r[result['dimension']]}**: **{r[result['metric']]:,.2f}**" for r in top_list])
        worst_details = "\n".join([f"  - **{r[result['dimension']]}**: **{r[result['metric']]:,.2f}**" for r in worst_list])
        filter_text = f" for **{filter_val}** ({filter_col})" if filter_val else ""
        year_text = f" in **{year}**" if year else ""
        
        answer = (
            f"### Performance Ranking of **{dimension}** by **{metric}**{filter_text}{year_text}\n\n"
            f"- **Top Performers**:\n{top_details}\n"
            f"- **Underperformers**:\n{worst_details}"
        )
        chart_spec = _maybe_chart("top_bottom_performers", result)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["top_bottom_performers"]
        }
    # AA. Aggregation (Sum, Average, Total, Count)
    elif any(f" {k} " in f" {msg} " for k in ["sum", "total", "average", "avg", "mean", "collected", "earned", "gained"]) or any(k in msg for k in ["how many", "how much"]):
        # Check if this is actually a comparison breakdown (e.g., "by region", "versus")
        is_breakdown = any(k in msg for k in ["compare", "comparison", "breakdown", "share", "proportion", "distribution", "by", "versus", "vs"])
        if not is_breakdown:
            words_set = set(w.strip("?,.!") for w in msg.split())
            agg_type = "sum"
            if any(k in words_set for k in ["average", "avg", "mean"]):
                agg_type = "mean"
            elif any(k in words_set for k in ["count", "frequency"]) or "number of" in msg or "how many rows" in msg:
                agg_type = "count"
            elif "min" in msg or "lowest value" in msg:
                agg_type = "min"
            elif "max" in msg or "highest value" in msg:
                agg_type = "max"

            args = {"metric": metric, "agg": agg_type, "year": year}
            if filter_col and filter_val:
                args["filter_col"] = filter_col
                args["filter_val"] = filter_val

            result = _execute_tool(df, schema, "get_aggregate", args)
            if "error" in result:
                return {"answer": f"### Aggregation Error\n\n- **Error**: {result['error']}", "chart_spec": None, "tools_used": []}

            val = result["value"]
            filter_text = f" for **{filter_val}** ({filter_col})" if filter_val else ""
            year_text = f" in **{year}**" if year else ""
            
            # Format the output value nicely
            if agg_type == "count":
                formatted_val = f"{int(val):,}"
            else:
                formatted_val = f"{val:,.2f}"

            agg_names = {
                "sum": "Total",
                "mean": "Average",
                "count": "Count",
                "min": "Minimum",
                "max": "Maximum"
            }
            
            answer = (
                f"### {agg_names[agg_type]} of **{metric}**{filter_text}{year_text}\n\n"
                f"- **{agg_names[agg_type]} Value**: **{formatted_val}**\n"
                f"- **Filtered Records Count**: {result['row_count']} row(s)"
            )
            chart_spec = _maybe_chart("get_aggregate", result)
            return {
                "answer": answer,
                "chart_spec": chart_spec,
                "tools_used": ["get_aggregate"]
            }

    # D. Compare/Distribution/Breakdown
    elif any(k in msg for k in ["compare", "comparison", "breakdown", "share", "proportion", "distribution", "by", "versus", "vs", "pie", "piechart", "pie-chart", "doughnut", "map", "global", "world", "country", "countries"]):
        if not dimension:
            return {"answer": "### Comparison Warning\n\n- **Missing Dimension**: To compare data, a categorical column is required but none was found.", "chart_spec": None, "tools_used": []}
        
        # User specified or auto-selected Chart.js type based on text
        if any(k in msg for k in ["pie", "piechart", "pie-chart", "doughnut", "share", "proportion", "breakdown", "distribution"]):
            chart_type = "pie"
        elif any(k in msg for k in ["map", "global", "world", "country", "countries", "geochart"]):
            chart_type = "map"
        else:
            chart_type = "bar"
            
        args = {"dimension": dimension, "metric": metric, "chart_type": chart_type, "year": year}
        if filter_col and filter_val:
            args["filter_col"] = filter_col
            args["filter_val"] = filter_val
        result = _execute_tool(df, schema, "compare_dimension", args)
        if "error" in result:
            return {"answer": f"### Comparison Error\n\n- **Error**: {result['error']}", "chart_spec": None, "tools_used": []}
        
        best = result["best"]
        worst = result["worst"]
        best_share = best.get('share_pct', 0)
        worst_share = worst.get('share_pct', 0)
        filter_text = f" for **{filter_val}** ({filter_col})" if filter_val else ""
        year_text = f" in **{year}**" if year else ""
        answer = (
            f"### Comparison Analysis of **{metric}** across **{dimension}**{filter_text}{year_text}\n\n"
            f"- **Dominant Segment**: **{best[result['dimension']]}** (generating **{best[result['metric']]:,.2f}**, representing **{best_share}%** share)\n"
            f"- **Lowest Segment**: **{worst[result['dimension']]}** (generating **{worst[result['metric']]:,.2f}**, representing **{worst_share}%** share)"
        )
        chart_spec = ve.comparison_to_chart(result, chart_type=chart_type)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["compare_dimension"]
        }

    # E. Compare Dimension (If dimension is identified and not handled by other specific intents)
    elif dimension:
        chart_type = "pie" if any(k in msg for k in ["pie", "doughnut", "share", "proportion", "breakdown"]) else "bar"
        args = {"dimension": dimension, "metric": metric, "chart_type": chart_type, "year": year}
        if filter_col and filter_val:
            args["filter_col"] = filter_col
            args["filter_val"] = filter_val
        result = _execute_tool(df, schema, "compare_dimension", args)
        if "error" not in result:
            best = result["best"]
            worst = result["worst"]
            best_share = best.get('share_pct', 0)
            worst_share = worst.get('share_pct', 0)
            filter_text = f" for **{filter_val}** ({filter_col})" if filter_val else ""
            year_text = f" in **{year}**" if year else ""
            answer = (
                f"### Breakdown of **{metric}** by **{dimension}**{filter_text}{year_text}\n\n"
                f"- **Top Performer**: **{best[result['dimension']]}** (generating **{best[result['metric']]:,.2f}**, representing **{best_share}%** share)\n"
                f"- **Lowest Performer**: **{worst[result['dimension']]}** (generating **{worst[result['metric']]:,.2f}**, representing **{worst_share}%** share)"
            )
            chart_spec = ve.comparison_to_chart(result, chart_type=chart_type)
            return {
                "answer": answer,
                "chart_spec": chart_spec,
                "tools_used": ["compare_dimension"]
            }

    # F. Trend (Default fallback if nothing else matched)
    else:
        args = {"metric": metric, "year": year}
        if filter_col and filter_val:
            args["filter_col"] = filter_col
            args["filter_val"] = filter_val
        result = _execute_tool(df, schema, "get_trend", args)
        if "error" in result:
            return {"answer": f"### Trend Analysis Error\n\n- **Error**: {result['error']}", "chart_spec": None, "tools_used": []}
        
        direction = result["direction"]
        change = result["latest_change_pct"]
        filter_text = f" for **{filter_val}** ({filter_col})" if filter_val else ""
        year_text = f" in **{year}**" if year else ""
        if change is not None:
            pct_str = f"changed by {change:+.2f}%"
            answer = (
                f"### Trend Analysis for **{metric}**{filter_text}{year_text}\n\n"
                f"- **Overall Direction**: **{direction.capitalize()}** trend\n"
                f"- **Recent Change**: **{pct_str}** compared to the prior period"
            )
        else:
            answer = (
                f"### Trend Timeline for **{metric}**{filter_text}{year_text}\n\n"
                f"- **Overall Direction**: **{direction.capitalize()}** trend\n"
                f"- **Status**: Timeline successfully generated and plotted below"
            )
        
        chart_spec = _maybe_chart("get_trend", result)
        return {
            "answer": answer,
            "chart_spec": chart_spec,
            "tools_used": ["get_trend"]
        }
