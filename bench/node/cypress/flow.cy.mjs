// Cypress arm: the same six steps, idiomatic Cypress.
describe("bench target", () => {
  it("adds a named row", () => {
    cy.visit("/index.html");
    cy.contains("button", /^inc$/).click();
    cy.get("#count").should("have.text", "1");
    cy.get('input[placeholder="name"]').type("alice");
    cy.contains("button", /^add$/).click();
    cy.get("#list li").last().should("have.text", "row-alice");
  });
});
