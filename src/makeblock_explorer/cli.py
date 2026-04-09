"""MakeBlock Explorer interactive CLI."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt

from .transport import scan_serial_ports, SerialTransport
from .protocol import Action, build_packet, parse_packet, find_packets
from .registry import DeviceRegistry, DeviceProfile


console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """MakeBlock FF55 Protocol Explorer CLI."""
    if ctx.invoked_subcommand is None:
        interactive_menu()


@main.command()
def scan():
    """Scan for connected MakeBlock devices."""
    do_scan()


@main.command()
@click.argument("port")
def explore(port: str):
    """Show device profile and capabilities for a connected device."""
    do_explore(port)


@main.command()
@click.argument("port")
@click.argument("device_id", type=str)  # hex like "0x08"
@click.argument("data", required=False, default="")
def raw(port: str, device_id: str, data: str):
    """Send a raw FF55 GET packet and display the response.

    DEVICE_ID: hex device type (e.g., 0x08)
    DATA: optional hex data payload (e.g., "0102FF")
    """
    do_raw_send(port, device_id, data)


def interactive_menu():
    """Main interactive numbered menu loop."""
    console.print(Panel.fit(
        "[bold cyan]MakeBlock FF55 Protocol Explorer[/bold cyan]",
        subtitle="v0.1.0"
    ))

    registry = DeviceRegistry.default()
    transport = SerialTransport()
    connected_port: str | None = None

    while True:
        console.print()
        console.print("[bold]Main Menu[/bold]")
        console.print("1. Scan for devices")
        console.print("2. Connect to device")
        console.print("3. Explore device (show profile)")
        console.print("4. Send raw FF55 packet")
        console.print("5. List known device profiles")
        console.print("0. Exit")
        console.print()

        if connected_port:
            console.print(f"[green]Connected:[/green] {connected_port}")
        else:
            console.print("[dim]Not connected[/dim]")

        try:
            choice = IntPrompt.ask("Choose", choices=["0", "1", "2", "3", "4", "5"])
        except (KeyboardInterrupt, EOFError):
            break

        if choice == 0:
            if transport.is_connected:
                transport.disconnect()
            break
        elif choice == 1:
            do_scan()
        elif choice == 2:
            connected_port = do_connect(transport)
        elif choice == 3:
            do_explore_interactive(registry)
        elif choice == 4:
            do_raw_interactive(transport, connected_port)
        elif choice == 5:
            do_list_profiles(registry)


def do_scan():
    """Scan and display found devices."""
    console.print("\n[bold]Scanning for MakeBlock devices...[/bold]")
    devices = scan_serial_ports()

    if not devices:
        console.print("[yellow]No MakeBlock devices found.[/yellow]")
        console.print("[dim]Tip: Check USB connection and CH340 drivers.[/dim]")
        return

    table = Table(title="Found Devices")
    table.add_column("Port", style="cyan")
    table.add_column("Description", style="green")
    table.add_column("VID:PID", style="dim")
    table.add_column("Serial", style="dim")

    for dev in devices:
        vid_pid = f"{dev.vid:04X}:{dev.pid:04X}" if dev.vid else "N/A"
        table.add_row(dev.port, dev.description, vid_pid, dev.serial_number or "N/A")

    console.print(table)


def do_connect(transport: SerialTransport) -> str | None:
    """Connect to a device by COM port."""
    devices = scan_serial_ports()

    if not devices:
        console.print("[yellow]No devices found. Plug in a device and try again.[/yellow]")
        return None

    console.print("\n[bold]Available devices:[/bold]")
    for i, dev in enumerate(devices, 1):
        console.print(f"  {i}. {dev.port} - {dev.description}")

    try:
        idx = IntPrompt.ask(
            "Select device",
            choices=[str(i) for i in range(1, len(devices) + 1)],
        )
        device = devices[idx - 1]

        if transport.is_connected:
            transport.disconnect()

        transport.connect(device.port)
        console.print(f"[green]Connected to {device.port}[/green]")
        return device.port
    except Exception as e:
        console.print(f"[red]Connection failed: {e}[/red]")
        return None


def do_explore_interactive(registry: DeviceRegistry):
    """Show device profile interactively."""
    devices = registry.list_devices()
    if not devices:
        console.print("[yellow]No device profiles loaded.[/yellow]")
        return

    console.print("\n[bold]Known device profiles:[/bold]")
    for i, name in enumerate(devices, 1):
        console.print(f"  {i}. {name}")

    try:
        idx = IntPrompt.ask(
            "Select device",
            choices=[str(i) for i in range(1, len(devices) + 1)],
        )
        profile = registry.get(devices[idx - 1])
        if profile:
            show_profile(profile)
    except (KeyboardInterrupt, EOFError):
        return


def show_profile(profile: DeviceProfile):
    """Display a device profile with sensors and actuators."""
    console.print(Panel(
        f"[bold]{profile.name}[/bold]\n"
        f"Chip: {profile.chip}\n"
        f"{profile.description}\n"
        f"Transport: {', '.join(profile.transport)}",
        title="Device Profile"
    ))

    if profile.sensors:
        table = Table(title="Sensors")
        table.add_column("Name", style="cyan")
        table.add_column("Device ID", style="yellow")
        table.add_column("Description")
        table.add_column("Readings", style="dim")

        for name, sensor in profile.sensors.items():
            readings_str = ", ".join(
                f"{r.name} ({r.type}, {r.unit})" for r in sensor.readings
            )
            table.add_row(
                name, f"0x{sensor.device_id:02X}", sensor.description, readings_str
            )

        console.print(table)

    if profile.actuators:
        table = Table(title="Actuators")
        table.add_column("Name", style="cyan")
        table.add_column("Device ID", style="yellow")
        table.add_column("Description")
        table.add_column("Parameters", style="dim")

        for name, actuator in profile.actuators.items():
            params_str = ", ".join(
                f"{p.name} ({p.type})" for p in actuator.parameters
            )
            table.add_row(
                name,
                f"0x{actuator.device_id:02X}",
                actuator.description,
                params_str,
            )

        console.print(table)


def do_raw_interactive(transport: SerialTransport, connected_port: str | None):
    """Send raw FF55 packet interactively."""
    if not transport.is_connected:
        console.print(
            "[yellow]Not connected. Connect to a device first (option 2).[/yellow]"
        )
        return

    console.print("\n[bold]Send Raw FF55 Packet[/bold]")
    console.print("[dim]Action types: GET=1, RUN=2, RESET=4, START=5[/dim]")

    try:
        action_val = IntPrompt.ask("Action (1=GET, 2=RUN, 4=RESET, 5=START)")
        action = Action(action_val)

        device_hex = Prompt.ask("Device ID (hex, e.g., 0x08)")
        device_id = int(device_hex, 16)

        data_hex = Prompt.ask("Data payload (hex, empty for none)", default="")
        data = bytes.fromhex(data_hex) if data_hex else b""

        # Build and send
        packet = build_packet(index=1, action=action, device=device_id, data=data)

        console.print(f"\n[dim]TX: {' '.join(f'{b:02X}' for b in packet)}[/dim]")
        transport.send(packet)

        # Wait for response
        response = transport.receive(timeout=2.0)
        if response:
            console.print(
                f"[green]RX: {' '.join(f'{b:02X}' for b in response)}[/green]"
            )

            # Try to parse
            packets = find_packets(response)
            if packets:
                pkt = packets[0][0]
                console.print(
                    f"  Index: {pkt.index}, Action: {pkt.action.name}, "
                    f"Device: 0x{pkt.device:02X}, Data: {pkt.data.hex()}"
                )
            else:
                console.print("[dim]  (could not parse as FF55 packet)[/dim]")
        else:
            console.print("[yellow]No response (timeout)[/yellow]")
    except (KeyboardInterrupt, EOFError):
        return
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def do_raw_send(port: str, device_id_hex: str, data_hex: str):
    """Send a raw FF55 GET packet (non-interactive command)."""
    device_id = int(device_id_hex, 16)
    data = bytes.fromhex(data_hex) if data_hex else b""

    transport = SerialTransport()
    try:
        transport.connect(port)
        packet = build_packet(
            index=1, action=Action.GET, device=device_id, data=data
        )

        console.print(f"[dim]TX: {' '.join(f'{b:02X}' for b in packet)}[/dim]")
        transport.send(packet)

        response = transport.receive(timeout=2.0)
        if response:
            console.print(
                f"[green]RX: {' '.join(f'{b:02X}' for b in response)}[/green]"
            )
            packets = find_packets(response)
            if packets:
                pkt = packets[0][0]
                console.print(
                    f"Index: {pkt.index}, Action: {pkt.action.name}, "
                    f"Device: 0x{pkt.device:02X}, Data: {pkt.data.hex()}"
                )
        else:
            console.print("[yellow]No response[/yellow]")
    finally:
        transport.disconnect()


def do_explore(port: str):
    """Non-interactive explore command."""
    registry = DeviceRegistry.default()
    devices = registry.list_devices()

    console.print(f"\n[bold]Exploring device on {port}[/bold]")
    console.print(f"Known profiles: {', '.join(devices)}")

    for name in devices:
        profile = registry.get(name)
        if profile:
            show_profile(profile)


def do_list_profiles(registry: DeviceRegistry):
    """List all known device profiles."""
    devices = registry.list_devices()
    if not devices:
        console.print("[yellow]No device profiles loaded.[/yellow]")
        return

    table = Table(title="Known Device Profiles")
    table.add_column("Name", style="cyan bold")
    table.add_column("Chip", style="green")
    table.add_column("Sensors", justify="right")
    table.add_column("Actuators", justify="right")
    table.add_column("Transport")

    for name in devices:
        profile = registry.get(name)
        if profile:
            table.add_row(
                profile.name,
                profile.chip,
                str(len(profile.sensors)),
                str(len(profile.actuators)),
                ", ".join(profile.transport),
            )

    console.print(table)
