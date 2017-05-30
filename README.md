Holster is a dict-like data structure that exposes its items as attributes, and provides easy access
to objects deep into nested structures with a minimum of syntactic noise. See the tests for
examples.

I wrote this out of a general frustration with the noise and distraction in the Pythonic style, but
the final straw that made me sit down and write this is the awful lack of facilities for managing
collections of variables. In particular, I work with symbolic computation packages a lot, in which
you set up a giant symbolic computation graph and wish to compute the values of subsets of the
nodes in the graph. We often end up writing code like this:

```
var_loss, var_error, var_and, var_many, var_other, var_things = construct_symbolic_graph(var_x, var_y)
agg_loss, agg_error, agg_and, agg_many, agg_other, agg_things = (
    MeanAggregate(), MeanAggregate(), MeanAggregate(), SumAggregate(), LastAggregate(), LastAggregate())
...
for batch in data:
  val_loss, val_error, val_and, val_many, val_other, val_things = compute(var_loss, var_error, var_and, var_many, var_other, var_things)
  for agg, val in zip([agg_loss, agg_error, agg_and, agg_many, agg_other, agg_things],
                      [val_loss, val_error, val_and, val_many, val_other, val_things]):
    agg.add(val)
...
record(agg_loss, agg_error, agg_and, agg_many, agg_other, agg_things)
```

This is verbose, but worse, it's not DRY. The subset of variables to extract from the symbolic
graph, compute and aggregate is repeated all over the place. These three sets of variable names are
better-chosen than ones you'll see in the wild; here it's clear that they are three sets of related
variables.

With Holster, I've come to write this as follows:

```
variables = construct_symbolic_graph(inputs)
aggregates = H(loss=MeanAggregate(),
               error=MeanAggregate(),
	       and=MeanAggregate(),
	       many=SumAggregate(),
	       other=LastAggregate(),
	       things=LastAggregate())
...
for batch in data:
    values = compute(variables.Narrow(" ".join(aggregates.Keys())))
    for aggregate, value in aggregates.Zip(values):
      aggregate.add(value)
...
record(aggregates)
```

That's right, Holster is just a dict on steroids; it facilitates bulk manipulation of nested
hierarchies of variables. I do this all over the place, so Holster is intended to be syntactically
lightweight, with none of the ["lovely"] ["Pythonic"] ["dict"] ["noise"] or ["comma-separated",
"lists", "of", "strings"]. Unfortunately due to unreliable kwarg ordering you might find yourself
having to use this [("particularly", "hateful"), ("list", "of"), ("key", "value"), ("pair",
"initialization")].  I'm looking for a way around it.

Besides this example, I also use Holster for (nested) hyperparameter management, multiple return
values, simulating dynamic variables, and anything else where otherwise everyone along the call
stack would have to be aware of everyone else's call signatures.

To avoid name clashes, keys are restricted to be lower-case, leaving upper-case for methods. I find
this restriction isn't so severe given Holster's purpose of managing what are basically variable
names.

Where it makes sense, methods that take a key can take it in the following forms:

  - a simple key representing a single attr lookup: "attr1"
  - a composition of simple keys: "attr1.attr2.attr3"
  - a disjunction of space-separated alternatives: "attr1 attr2.attr3"
