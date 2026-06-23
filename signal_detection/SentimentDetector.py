import asyncio
import openai


class SentimentDetector:
    SYSTEM_PROMPT = """
You are a sentiment classifier for financial and political news.

Your task: given a TARGET EVENT and a NEWS HEADLINE, output a single integer rating indicating how much the news supports or prevents the target event from occurring.

Rating scale:
-2 = The news strongly suggests the event will NOT happen (direct prevention or reversal)
-1 = The news suggests development away from the target event
 0 = The news is neutral or unrelated to the target event
+1 = The news gives momentum toward the target event happening
+2 = The news strongly indicates the target event is imminent or already occurring

Rules:
- Output ONLY one integer: -2, -1, 0, 1, or 2
- No explanation, no punctuation, no text — just the number
- If the headline is ambiguous, default to 0
"""

    def __init__(self):
        self.client = openai.AsyncOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",  # required but unused by Ollama
        )

    @property
    def TARGET_EVENT(self) -> str:
        return self._TARGET_EVENT

    @TARGET_EVENT.setter
    def TARGET_EVENT(self, value: str):
        self._TARGET_EVENT = value

    async def get_sentiment(self, headline: str) -> int:
        response = await self.client.responses.create(
            model="gemma3:4b",
            instructions=SentimentDetector.SYSTEM_PROMPT,
            input=f"TARGET EVENT: {self.TARGET_EVENT}\nHEADLINE: {headline}",
            max_output_tokens=5,  # enforce short output
            temperature=0.0,  # deterministic — critical for classifiers
        )
        rating = int(response.output[0].content[0].text.strip())
        return rating


async def main():
    s_detector = SentimentDetector()
    s_detector.TARGET_EVENT = r"Gavin Newsom wins presidential election 2028"
    headline_1 = r"""S&P, Nasdaq drop on tech selloff as concerns about hawkish Fed, AI spending mount
    The Nasdaq and the S&P 500 fell to over one-week lows on Tuesday, dragged down by sharp losses in semiconductor stocks as ​investors braced for a more hawkish Federal Reserve and scrutinized growing debt-funded AI spending.
    """
    headline_2 = r"""US Supreme Court limits scope of foreign human rights claims\n Justices refuse to consider complaint alleging Cisco enabled Chinese surveillance of banned religious group"""

    tasks = [
        asyncio.create_task(s_detector.get_sentiment(headline_1)),
        asyncio.create_task(s_detector.get_sentiment(headline_2)),
    ]

    ratings = await asyncio.gather(*tasks)
    print(ratings)


if __name__ == "__main__":
    asyncio.run(main())
