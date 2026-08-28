from testence.engine import Target


INCREMENT = Target("role", "button", name="inc")
COUNTER = Target("css", "#count")
NAME = Target("placeholder", "name")
ADD = Target("role", "button", name="add")
LAST_ROW = Target("css", "#list li")


def test_add_a_named_row(ex):
    ex.goto("/index.html", intent="open the page")
    ex.click(INCREMENT, intent="increment the counter")
    ex.expect_text(COUNTER, "1", intent="counter shows 1")
    ex.fill(NAME, "alice", intent="enter a name")
    ex.click(ADD, intent="add the named row")
    ex.expect_text(LAST_ROW, "row-alice", intent="the named row appears")
