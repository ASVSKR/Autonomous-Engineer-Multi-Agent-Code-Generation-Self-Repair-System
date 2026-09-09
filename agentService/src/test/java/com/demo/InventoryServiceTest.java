```java
package com.demo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class InventoryServiceTest {

    @Mock
    private RestTemplate restTemplate;

    @InjectMocks
    private InventoryService inventoryService;

    @Test
    public void testUpdateQuantity() {
        // Arrange
        Item item = new Item();
        item.setQuantity(10);

        when(restTemplate.postForObject("http://localhost:8080/git/clone", null, String.class)).thenReturn("Git clone successful");
        when(restTemplate.postForObject("http://localhost:8080/git/pull", null, String.class)).thenReturn("Git pull successful");
        when(restTemplate.postForObject("http://localhost:8080/jira/create", any(JiraIssue.class), String.class)).thenReturn("Jira issue created successfully");
        when(restTemplate.getForObject("http://localhost:8080/jira/getOpenTicket", List.class)).thenReturn(new ArrayList<>());
        when(restTemplate.postForObject("http://localhost:8080/jira/updateStatus/ISSUE-123", null, String.class)).thenReturn("Jira issue status updated successfully");
        when(restTemplate.getForObject("http://localhost:8080/jira/issue/ISSUE-123", JiraIssue.class)).thenReturn(new JiraIssue("Inventory update", "Inventory quantity updated"));
        when(restTemplate.postForObject("http://localhost:8080/jira/issue/ISSUE-123/attachments", null, String.class)).thenReturn("Jira attachment uploaded successfully");
        when(restTemplate.postForObject("http://localhost:8080/jira/issue/ISSUE-123/comment", null, String.class)).thenReturn("Jira comment added successfully");

        // Act
        ResponseEntity<String> response = inventoryService.updateQuantity(item);

        // Assert
        assertNotNull(response);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Inventory quantity updated to 9", response.getBody());
    }

    @Test
    public void testUpdateQuantity_InvalidItem() {
        // Act
        ResponseEntity<String> response = inventoryService.updateQuantity(null);

        // Assert
        assertNotNull(response);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Inventory quantity updated to -1", response.getBody());
    }
}
```