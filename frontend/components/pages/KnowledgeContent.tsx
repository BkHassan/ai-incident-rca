import { EmptyState } from "@/components/ui/Section";
import { Body, Kicker, PageTitle } from "@/components/ui/Type";

export function KnowledgeContent() {
  return (
    <div className="stack">
      <header className="page-head">
        <Kicker>Knowledge</Kicker>
        <PageTitle>Retrieval collections</PageTitle>
        <Body>
          Historical incidents and technical notes are searched inside an investigation. There is no knowledge
          API, so this page does not list documents or pretend to search them.
        </Body>
      </header>
      <EmptyState title="No knowledge browser">
        The index, when built, has two collections: historical_incidents and technical_documents. Hits are not
        returned on their own route. A similar-incident note appears only on a completed RCA result.
      </EmptyState>
    </div>
  );
}
