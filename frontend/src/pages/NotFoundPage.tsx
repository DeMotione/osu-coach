import { Link } from "react-router";

import { EmptyState } from "../components/states";
import { Card, Page } from "../components/ui";

export default function NotFoundPage() {
  return (
    <Page title="Page not found">
      <Card>
        <EmptyState
          title="There is no page here"
          action={
            <Link className="btn btn--primary" to="/replays">
              Go to Replays
            </Link>
          }
        />
      </Card>
    </Page>
  );
}
