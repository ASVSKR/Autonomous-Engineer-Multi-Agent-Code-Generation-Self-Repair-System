```java
package com.demo;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.List;

@Service
public class LibraryService {

    private final RestTemplate restTemplate;

    @Autowired
    public LibraryService(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public List<String> getAvailableBooks(String issueId) {
        // Assuming the Jira service is running on the same host as this service
        String jiraServiceUrl = "http://localhost:8080";
        String url = jiraServiceUrl + "/jira/issue/" + issueId;

        ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
        if (response.getStatusCode().is2xxSuccessful()) {
            // Assuming the response body contains the list of available books
            // For simplicity, this example assumes the response body is a comma-separated list of book titles
            String responseBody = response.getBody();
            if (responseBody != null) {
                return List.of(responseBody.split(","));
            } else {
                return List.of();
            }
        } else {
            return List.of();
        }
    }

    public static void main(String[] args) {
        System.setProperty("JAVA_HOME", "/path/to/jdk");
        LibraryService libraryService = new LibraryService(new RestTemplate());
        libraryService.getAvailableBooks("issueId");
    }
}
```