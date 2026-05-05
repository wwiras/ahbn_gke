# GKE Exp Guideline

What you should avoid is trying to make the first working AHBN logic inside the cloud-native environment. That usually slows everything down because when something fails, you won’t know whether the problem is:

* AHBN control logic
* message dissemination logic
* cluster logic
* async networking
* container orchestration
* deployment/configuration

That is exactly the kind of confusion that makes RO3 painful.

The better approach is this:

Phase 1: Build AHBN in plain Python
Use the same spirit as RO2. This is where you develop and debug:

* adaptive control weight
* gossip/cluster mode switching
* forwarding logic
* duplicate suppression behavior
* early Exp7 and Exp8

Why plain Python first? Because it gives you:

* faster iteration
* easier debugging
* easier plotting
* easier fair comparison with RO2 baselines
* cleaner academic explanation

In other words, plain Python is where you prove:

“AHBN as a protocol idea works.”

Then:

Phase 2: Port the stable AHBN into the cloud-native simulator
After the logic is stable, move it into your RO1 simulator for:

* overload/failure realism
* churn realism
* heterogeneous resource validation
* Kubernetes-based demonstrations
* RO1 + RO3 integration

This is where you prove:

“AHBN still works under realistic cloud-native conditions.”

So the correct division is:

* Plain Python = protocol design and early validation
* Cloud-native simulator = realism and final validation

That actually matches your experiment table very well.

For RO3, I would execute it like this:

First in plain Python

* Exp7: AHBN vs Gossip
* Exp9: AHBN under Dense Topologies

These are the best first experiments because they mainly test protocol behavior, not infrastructure realism.

Then in cloud-native simulator

* Exp8: AHBN vs Cluster under bottleneck
* Exp10: AHBN under Failure / Overload
* Exp11: AHBN under Churn
* Exp12: AHBN under Mixed Resources

These are the experiments where Kubernetes and cloud-native orchestration add real value.

So the answer to your question is:

Do not start RO3 directly in the cloud-native simulator.
Start AHBN in plain Python, make it work, validate the core behavior, then integrate it into the cloud-native simulator for realistic evaluation.

A good mental model is:

* RO1 built the laboratory
* RO2 identified the disease
* RO3 now develops the treatment

You do not invent the treatment first inside the most complicated laboratory setup.
You first make sure the treatment itself works.

If you want the cleanest thesis wording for this decision, you can say:

The AHBN protocol is first developed and validated in a simplified plain-Python simulation environment to enable rapid prototyping, controlled debugging, and fair comparison with the RO2 baselines. Once the protocol behavior is stabilized, it is integrated into the cloud-native simulator developed in RO1 for realistic validation under failure, churn, and heterogeneous resource conditions.

That sentence is academically strong and fully defensible.

My direct recommendation is:

1. implement minimal AHBN in plain Python
2. reproduce one success case against gossip
3. reproduce one success case against cluster
4. then port the same logic into your cloud-native simulator

That is the correct path.

I can turn this into a decision table: which RO3 experiment should run in plain Python vs cloud-native simulator, with justification for each.