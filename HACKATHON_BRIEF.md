# Inside the Game: Developer Hackathon — Official Brief (copied from the hackathon site)

Hosted by Microsoft with the Premier League. Event period: Sep 29 – Nov 21, 2026.
- Submissions open: Oct 6
- **Submissions close: Oct 27**
- Winners announced: Nov 20

## Data requirement
Projects must use synthetic, football-realistic data. No real Premier League match data is redistributed to participants. (No dataset is provided; participants create their own.)

## Challenge: The Synthetic Match Insights Engine for Premier League Studio
An AI insights engine running on Azure that explains the game beyond the stats, turning football events into real-time insights, key narratives and recaps, personalized for every fan, for studio and streaming use.

Build AI-driven applications and agents that transform synthetic football events into explainable match intelligence: surface meaningful stats, identify key moments, explain why they matter, and generate personalized experiences. The project may be an AI agent, workflow, integration, data platform, analytics experience, automation solution or a new experience. It should be responsive enough for live play and clear enough for real-time narratives and automated recaps in studio, broadcast or streaming scenarios. It should also be flexible enough for fans in any market to tailor their experience.

### (i) One pipeline with five stages
- (a) **Ingest** synthetic match events as they happen (passes, shots, tackles, possession changes, pressure events, match metadata, etc.).
- (b) **Interpret** them into meaningful football statistics, patterns and the context behind them.
- (c) **Explain** why a moment matters rather than only reporting that it happened.
- (d) **Render** that insight into something that can sit on screen alongside the match.
- (e) **Personalize** it, so the same intelligence reaches a data-hungry analyst and a casual fan as two genuinely different experiences.
  - Examples: customized modes, favorite club(s), favorite player(s), a player-focused mode that follows one player throughout the match, and more.
  - Outputs may focus on on-screen storytelling that is timed and machine-readable enough to render as synchronized graphical overlays on a live match feed, as the platform's rendering partner does in the production path.
  - Alternatively they may focus on personalized audience experiences: viewing modes shaped by language, favorite club, favorite player, or a single performance metric.
  - Or both. A project that only generates metrics has no audience, and one that only personalizes has nothing to personalize.

### (ii) Real-time match intelligence
Ingest synthetic match events and aggregate them into meaningful football states and statistics. Features to consider:
- **Player identification**: real-time player name tagging, with optional speed and distance indicators triggered at predefined thresholds.
- **Pass quality**: pass distance, pass accuracy and a pass difficulty rating.
- **Speed metrics**: ball speed and shot speed.
- **Auto-eventing**: running a model over an incoming video feed to generate the pass and speed metrics automatically (optional; no video is provided).

### (iii) Narrative generation
Go beyond metrics to produce key narratives, player-performance context, notable milestones and match recaps.

### (iv) Explainability
Explain why moments matter, such as control vs chaos, tactical pressure changes and game rhythm patterns.

### (v) Data innovation
Create or extend synthetic, football-realistic datasets with events such as passes, shots, tackles, possession changes, pressure events and match metadata.

### (vi) Multi-language storytelling
Generate clear natural-language outputs that could support global studio and streaming scenarios in multiple languages.

## Prize categories
- **Grand Prize, 1st place**: $4,000 per team member, a Premier League match digital ticket, a store voucher, and social promotion. The best overall solution, with real-world impact and innovative use of the Microsoft AI platform stack.
- **Grand Prize, 2nd place**: $2,500 per team member, plus the ticket, voucher and promotion.
- Each category prize below is $1,500 per team member plus a voucher and promotion.
  - **Best Use of Microsoft Foundry**: most effective use of Foundry to accelerate development, orchestration and management of AI solutions.
  - **Best Enterprise Solution**: strongest readiness for enterprise deployment and long-term business impact; reliability, transparency and the controls needed for production.
  - **Best Multi-Agent Orchestration**: purposeful multi-agent collaboration using GitHub Copilot, Microsoft Agent Framework, A2A, or another supported orchestration approach. Judges assess whether agents have distinct roles, coordinate through shared state and effective handoffs, recover from failures, and deliver an end-to-end outcome a single agent could not.
  - **Best Azure Cloud Native Integration**: AKS, Azure Container Apps, Functions, Logic Apps and AI-optimized data platforms; event-driven architecture, automation, operational excellence and measurable business impact.

## Submission requirements
- A newly built project that meets the requirements.
- A project pitch or description: what you built, which Microsoft and Azure technologies you used, what it does, and what problem it solves.
- A demo video:
  - **under 2 minutes**, showing the project working on its target platform;
  - published at a public URL (YouTube, Vimeo, Facebook Video or Youku) on the project page;
  - with **no third-party trademarks or copyrighted music** unless you have permission.
- A **public** GitHub repository URL.

## Judging rubric (20% each)
1. **Technological implementation**: quality engineering practices, effective use of hero technologies, well-structured, documented and maintainable code.
2. **Agentic design and innovation**: creative agentic patterns, sophisticated orchestration or multi-agent collaboration, novel AI implementation.
3. **Real-world impact and applicability**: significance of the problem, production deployment readiness, potential impact.
4. **User experience and presentation**: intuitive UX, clear communication of value in the demo, balanced frontend and backend.
5. **Adherence to the hackathon category.**

## Policies to check
Hackathon Rules (eligibility by country, exact deadline time zone, data rules), Code of Conduct, Security Policy.
