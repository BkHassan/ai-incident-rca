import { EmptyState } from "@/components/ui/Section";
import { Body, Kicker, PageTitle } from "@/components/ui/Type";

export function KnowledgeContent() {
  return (
    <div className="stack">
      <header className="page-head">
        <Kicker>Knowledge</Kicker>
        <PageTitle>Retrieval collections</PageTitle>
        <Body>
          Historical incidents and technical notes are retrieved for an investigation. This page does not search
          them and it is not a chat.
        </Body>
      </header>
      <EmptyState title="No knowledge browser">
        Open an incident investigation to see the historical incidents and technical chunks returned for that
        incident.
      </EmptyState>
    </div>
  );
}
