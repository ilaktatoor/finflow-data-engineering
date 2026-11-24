# Diagrams

All diagrams are Mermaid, embedded in the documents where they are explained,
so they render on GitHub and stay next to the text they illustrate:

| Diagram | Location |
|---|---|
| Component architecture | [architecture/overview.md](../architecture/overview.md#components) |
| Journey of one transaction (sequence) | [architecture/data-flow.md](../architecture/data-flow.md#the-journey-of-one-transaction) |
| Star schema (ER) | [architecture/data-model.md](../architecture/data-model.md) |
| Profiles and data lifecycle | [README](../../README.md#architecture) |

To export one as an image: `npx @mermaid-js/mermaid-cli -i diagram.mmd -o diagram.svg`
(not needed for GitHub).
