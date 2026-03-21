using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Net.Http;
using Windows.Devices.Enumeration;

class Program
{
    static HashSet<string> seenDevices = new HashSet<string>();
    static int deviceCount = 0;
    static DeviceWatcher watcher;
    static HttpClient httpClient = new HttpClient();
    static string flaskUrl = "http://127.0.0.1:5001/update_devices";

    // Method to send device count to Flask backend
    static async Task SendDeviceCountToFlask(int count)
    {
        try
        {
            var json = new { device_count = count };
            var content = new StringContent(System.Text.Json.JsonSerializer.Serialize(json), System.Text.Encoding.UTF8, "application/json");
            var response = await httpClient.PostAsync(flaskUrl, content);
            if (response.IsSuccessStatusCode)
            {
                Console.WriteLine($"Sent device count to Flask: {count}");
            }
            else
            {
                Console.WriteLine($"Failed to send to Flask: {response.StatusCode}");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error sending to Flask: {ex.Message}");
        }
    }

    static async Task Main(string[] args)
    {
        try
        {
            Console.WriteLine("Starting Bluetooth watcher...\n");

            var properties = new string[]
            {
                "System.Devices.Aep.DeviceAddress",
                "System.Devices.Aep.IsConnected",
                "System.Devices.Aep.IsPresent"
            };

            string aqsFilter = "System.Devices.Aep.ProtocolId:=\"{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}\"";

            watcher = DeviceInformation.CreateWatcher(
                aqsFilter,
                properties,
                DeviceInformationKind.AssociationEndpoint
            );

            // EXISTING DEVICES
            var devices = await DeviceInformation.FindAllAsync(
                aqsFilter,
                properties,
                DeviceInformationKind.AssociationEndpoint
            );

            Console.WriteLine($"Found {devices.Count} existing devices\n");

            foreach (var device in devices)
            {
                seenDevices.Add(device.Id);
                deviceCount++;

                string address = device.Properties.ContainsKey("System.Devices.Aep.DeviceAddress")
                    ? device.Properties["System.Devices.Aep.DeviceAddress"].ToString()
                    : "N/A";

                Console.WriteLine($"[EXISTING] {device.Name ?? "Unknown"}");
                Console.WriteLine($"  Address: {address}\n");
            }

            Console.WriteLine($"Total Count: {deviceCount}\n");
            Console.WriteLine("Now listening for new devices...\n");
            
            // Send initial device count to Flask
            await SendDeviceCountToFlask(deviceCount);

            // NEW DEVICES
            watcher.Added += (s, d) =>
            {
                if (!seenDevices.Contains(d.Id))
                {
                    seenDevices.Add(d.Id);
                    deviceCount++;

                    string address = d.Properties.ContainsKey("System.Devices.Aep.DeviceAddress")
                        ? d.Properties["System.Devices.Aep.DeviceAddress"].ToString()
                        : "N/A";

                    Console.WriteLine($"[NEW] {d.Name ?? "Unknown"}");
                    Console.WriteLine($"  Address: {address}");
                    Console.WriteLine($"  Total Count: {deviceCount}\n");
                    
                    // Send updated count to Flask (fire and forget)
                    _ = SendDeviceCountToFlask(deviceCount);
                }
            };

            // REMOVED DEVICES
            watcher.Removed += (s, d) =>
            {
                if (seenDevices.Contains(d.Id))
                {
                    seenDevices.Remove(d.Id);
                    deviceCount--;

                    Console.WriteLine($"[REMOVED] Device ID: {d.Id}");
                    Console.WriteLine($"  Total Count: {deviceCount}\n");
                    
                    // Send updated count to Flask (fire and forget)
                    _ = SendDeviceCountToFlask(deviceCount);
                }
            };

            // UPDATED DEVICES
            watcher.Updated += (s, d) =>
            {
                if (seenDevices.Contains(d.Id))
                {
                    bool isConnected = d.Properties.ContainsKey("System.Devices.Aep.IsConnected")
                        ? (bool)d.Properties["System.Devices.Aep.IsConnected"]
                        : false;

                    Console.WriteLine($"[UPDATE] Device ID: {d.Id} - Connected: {isConnected}\n");
                }
            };

            watcher.Start();

            Console.WriteLine("Scanning... Press Enter to stop\n");
            Console.ReadLine();

            watcher.Stop();
            Console.WriteLine("\nBluetooth watcher stopped.");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error: {ex.Message}");
        }
    }
}