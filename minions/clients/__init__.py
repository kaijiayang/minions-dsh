# NOTE: The top-level imports below are intentionally wrapped in try/except so that
# missing optional provider SDKs do NOT break importing this package.
# This is required for Python 3.13+ and minimal installs where only a few clients
# (e.g. openai/ollama/deepseek) are available. Unavailable clients are simply skipped.

def _safe_import(name, warn):
    try:
        module = __import__(name, fromlist=["*"])
        return module
    except ImportError as e:
        print(f"WARNING: {warn} ({name}: {e})")
        return None

from minions.clients.base import MinionsClient

for _mod, _names, _warn in [
    ("minions.clients.ollama", ("OllamaClient", "OllamaTurboClient"), "ollama not installed"),
    ("minions.clients.openai_compat", ("OpenAICompatClient", "PLATFORM_PRESETS", "SUPPORTED_PLATFORMS", "resolve_platform"), "openai not installed"),
    ("minions.clients.osaurus", ("OsaurusClient",), "osaurus not installed"),
    ("minions.clients.lemonade", ("LemonadeClient",), "lemonade not installed"),
    ("minions.clients.openai", ("OpenAIClient",), "openai not installed"),
    ("minions.clients.azure_openai", ("AzureOpenAIClient",), "azure-openai not installed"),
    ("minions.clients.anthropic", ("AnthropicClient",), "anthropic not installed"),
    ("minions.clients.cohere", ("CohereClient",), "cohere not installed"),
    ("minions.clients.together", ("TogetherClient",), "together not installed"),
    ("minions.clients.perplexity", ("PerplexityAIClient",), "perplexity not installed"),
    ("minions.clients.openrouter", ("OpenRouterClient",), "openrouter not installed"),
    ("minions.clients.groq", ("GroqClient",), "groq not installed"),
    ("minions.clients.deepseek", ("DeepSeekClient",), "deepseek not installed"),
    ("minions.clients.qwen", ("QwenClient",), "qwen not installed"),
    ("minions.clients.sambanova", ("SambanovaClient",), "sambanova not installed"),
    ("minions.clients.moonshot", ("MoonshotClient",), "moonshot not installed"),
    ("minions.clients.gemini", ("GeminiClient",), "gemini not installed"),
    ("minions.clients.grok", ("GrokClient",), "grok not installed"),
    ("minions.clients.mistral", ("MistralClient",), "mistral not installed"),
    ("minions.clients.minimax", ("MiniMaxClient",), "minimax not installed"),
    ("minions.clients.sarvam", ("SarvamClient",), "sarvam not installed"),
    ("minions.clients.docker_model_runner", ("DockerModelRunnerClient",), "docker model runner not installed"),
    ("minions.clients.distributed_inference", ("DistributedInferenceClient",), "distributed inference not installed"),
    ("minions.clients.novita", ("NovitaClient",), "novita not installed"),
    ("minions.clients.parallel", ("ParallelClient",), "parallel not installed"),
    ("minions.clients.tencent", ("TencentClient",), "tencent not installed"),
    ("minions.clients.cloudflare", ("CloudflareGatewayClient",), "cloudflare gateway not installed"),
    ("minions.clients.notdiamond", ("NotDiamondAIClient",), "notdiamond not installed"),
    ("minions.clients.vercel_gateway", ("VercelGatewayClient",), "vercel gateway not installed"),
    ("minions.clients.exa", ("ExaClient",), "exa not installed"),
    ("minions.clients.nousresearch", ("NousResearchClient",), "nousresearch not installed"),
    ("minions.clients.baseten", ("BasetenClient",), "baseten not installed"),
]:
    _m = _safe_import(_mod, _warn)
    if _m is not None:
        for _n in _names:
            if hasattr(_m, _n):
                globals()[_n] = getattr(_m, _n)

__all__ = [
    "OllamaClient",
    "OllamaTurboClient",
    "OpenAICompatClient",
    "OsaurusClient",
    "LemonadeClient",
    "OpenAIClient",
    "AzureOpenAIClient",
    "AnthropicClient",
    "CohereClient",
    "TogetherClient",
    "PerplexityAIClient",
    "OpenRouterClient",
    "GroqClient",
    "DeepSeekClient",
    "QwenClient",
    "SambanovaClient",
    "MoonshotClient",
    "GeminiClient",
    "GrokClient",
    "MistralClient",
    "MiniMaxClient",
    "SarvamClient",
    "DockerModelRunnerClient",
    "DistributedInferenceClient",
    "NovitaClient",
    "ParallelClient",
    "TencentClient",
    "CloudflareGatewayClient",
    "NotDiamondAIClient",
    "VercelGatewayClient",
    "ExaClient",
    "BasetenClient",
    "NousResearchClient",
]

try:
    from minions.clients.transformers import TransformersClient

    __all__.append("TransformersClient")
except ImportError:
    # print warning that transformers is not installed
    print(
        "WARNING: Transformers is not installed. Please install it with `pip install transformers`."
    )

try:
    from .cartesia_mlx import CartesiaMLXClient

    __all__.append("CartesiaMLXClient")
except ImportError:
    # If cartesia_mlx is not installed, skip it
    print(
        "Warning: cartesia_mlx is not installed. If you want to use cartesia_mlx, please follow the instructions in the README to install it."
    )

try:
    from .huggingface_client import HuggingFaceClient

    __all__.append("HuggingFaceClient")
except ImportError:
    # print warning that huggingface is not installed
    print(
        "Warning: huggingface inference client is not installed. If you want to use huggingface inference client, please install it with `pip install huggingface-hub`"
    )

# Import all MLX clients from the consolidated file
try:
    from .mlx_clients import MLXLMClient, MLXOmniClient, MLXAudioClient, MLXParallmClient
    __all__.extend(["MLXLMClient", "MLXOmniClient", "MLXAudioClient", "MLXParallmClient"])
except ImportError:
    # Individual client imports with their specific dependencies
    try:
        from .mlx_clients import MLXLMClient
        __all__.append("MLXLMClient")
    except ImportError:
        print(
            "Warning: mlx_lm is not installed. If you want to use mlx_lm, please install it with `pip install mlx-lm`."
        )

    try:
        from .mlx_clients import MLXOmniClient
        __all__.append("MLXOmniClient")
    except ImportError:
        print(
            "Warning: mlx_omni is not installed. If you want to use mlx_omni, please install it with `pip install mlx-omni-server`"
        )

    try:
        from .mlx_clients import MLXAudioClient
        __all__.append("MLXAudioClient")
    except ImportError:
        print(
            "Warning: mlx_audio is not installed. If you want to use mlx_audio, please install it with `pip install mlx-audio`"
        )

    try:
        from .mlx_clients import MLXParallmClient
        __all__.append("MLXParallmClient")
    except ImportError:
        print(
            "Warning: mlx_parallm is not installed. If you want to use mlx_parallm, please install it with `pip install mlx-parallm`"
        )


# Duplicate import removed - TransformersClient is already imported above

try:
    from minions.clients.secure import SecureClient
    __all__.append("SecureClient")
except ImportError:
    # print warning that secure crypto utilities are not available
    print(
        "Warning: Secure crypto utilities are not available. SecureClient will not be available. "
        "Please ensure the secure module is properly installed."
    )

try:
    from minions.clients.cerebras import CerebrasClient
    __all__.append("CerebrasClient")
except ImportError:
    # print warning that cerebras-cloud-sdk is not installed
    print(
        "Warning: cerebras-cloud-sdk is not installed. If you want to use CerebrasClient, "
        "please install it with `pip install cerebras-cloud-sdk`."
    )

try:
    from minions.clients.modular import ModularClient
    __all__.append("ModularClient")
except ImportError:
    # print warning that modular is not installed
    print(
        "Warning: Modular MAX or OpenAI client is not installed. If you want to use ModularClient, "
        "please install Modular MAX (https://docs.modular.com/max/get-started) and OpenAI client (pip install openai)."
    )

try:
    from minions.clients.lmcache import LMCacheClient
    __all__.append("LMCacheClient")
except ImportError:
    # print warning that lmcache is not installed
    print(
        "Warning: LMCache or vLLM is not installed. If you want to use LMCacheClient, "
        "please install with `pip install lmcache vllm`. "
        "For detailed instructions, see: https://docs.lmcache.ai/getting_started/installation.html"
    )
