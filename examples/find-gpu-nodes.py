import asyncio
import json
from tabulate import tabulate  # You may need to install this: pip install tabulate

from golem.node import GolemNode


async def do_scan():
    golem = GolemNode(app_key="o")
    await golem.start()

    print("Scanning for GPU nodes...")

    # Store the data for tabulation
    nodes_data = []

    async for it in golem.scan(constraints="(golem.runtime.name=vm-nvidia)", quick_scan=True):
        provider_id = it.providerId
        subnet = it.properties.get("golem.node.debug.subnet", "N/A")
        name = it.properties.get("golem.node.id.name", "N/A")
        gpu_model = it.properties.get("golem.!exp.gap-35.v1.inf.gpu.model", "N/A")

        # Add data to our list
        nodes_data.append([provider_id, name, gpu_model, subnet])

    # Print elegant table if we found any nodes
    if nodes_data:
        headers = ["Provider ID", "Node Name", "GPU Model", "Subnet"]
        print("\nFound GPU Nodes:")
        print(tabulate(nodes_data, headers=headers, tablefmt="pretty"))
        print(f"\nTotal nodes found: {len(nodes_data)}")
    else:
        print("\nNo GPU nodes found.")

    print("\nScan completed.")
    await golem.aclose()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(do_scan())
